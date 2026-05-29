from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from azure.communication.callautomation import (
    CallAutomationClient,
    PhoneNumberIdentifier,
    TextSource,
)
from src.agents.orchestrator import DEFAULT_AZURE_OPENAI_DEPLOYMENT, OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.message_history import MessageHistory
from src.models.order import Order, OrderSource, OrderStatus
from src.models.session import OrderSession
from src.services.channel_locks import get_channel_user_lock
from src.services.message_history_logger import (
    build_message_history_id,
    get_message_history_repo,
    save_message,
)
from src.services.tenant_resolver import resolve_tenant_for_phone

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2
HISTORY_CONTEXT_LIMIT = 20
MAX_TURNS = 10
GREETING_MESSAGE = "お電話ありがとうございます。ご注文内容をお話しください。"
GOODBYE_MESSAGE = "ご注文ありがとうございました。失礼いたします。"
RETRY_MESSAGE = "すみません、聞き取れませんでした。もう一度お願いいたします。"
TTS_VOICE = "ja-JP-NanamiNeural"
PHONE_SYNC_AI_TIMEOUT_SECONDS = 20.0
PHONE_SYNC_FALLBACK_MESSAGE = "ご注文内容を確認しています。受付は完了していますので、確認でき次第登録いたします。"


def _get_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%s; using %.1f", name, raw, default)
        return default


@dataclass
class CallState:
    call_connection_id: str
    server_call_id: str
    caller_number: str
    called_number: str
    tenant_ctx: TenantContext
    session: OrderSession | None = None
    turn_count: int = 0
    order_confirmed: bool = False
    last_order_id: str | None = None
    transcript_parts: list[str] = field(default_factory=list)
    audio_enabled: bool = True
    known_customer_id: str | None = None


class PhoneCallHandler:
    def __init__(
        self,
        callback_base_url: str,
        azure_openai_endpoint: str,
        azure_openai_key: str,
        speech_service_key: str,
        speech_service_endpoint: str | None = None,
        azure_openai_deployment_name: str = DEFAULT_AZURE_OPENAI_DEPLOYMENT,
    ):
        self._callback_base_url = callback_base_url.rstrip("/")
        self._openai_endpoint = azure_openai_endpoint
        self._openai_key = azure_openai_key
        self._openai_deployment_name = azure_openai_deployment_name
        self._speech_key = speech_service_key
        self._speech_endpoint = speech_service_endpoint
        self._phone_sync_ai_timeout_seconds = _get_float_env(
            "PHONE_SYNC_AI_TIMEOUT_SECONDS",
            PHONE_SYNC_AI_TIMEOUT_SECONDS,
        )
        self._calls: dict[str, CallState] = {}
        self._acs_clients: dict[str, CallAutomationClient] = {}

    def _get_acs_client(self, connection_string: str) -> CallAutomationClient:
        if connection_string not in self._acs_clients:
            self._acs_clients[connection_string] = CallAutomationClient.from_connection_string(connection_string)
        return self._acs_clients[connection_string]

    async def handle_event(self, event: dict) -> dict | None:
        event_type = event.get("type", "")

        if "IncomingCall" in event_type:
            return await self._handle_incoming_call(event)
        elif "CallConnected" in event_type:
            return await self._handle_call_connected(event)
        elif "RecognizeCompleted" in event_type:
            return await self._handle_recognize_completed(event)
        elif "RecognizeFailed" in event_type:
            return await self._handle_recognize_failed(event)
        elif "PlayCompleted" in event_type:
            return await self._handle_play_completed(event)
        elif "PlayFailed" in event_type:
            return await self._handle_play_failed(event)
        elif "CallDisconnected" in event_type:
            return await self._handle_call_disconnected(event)
        else:
            logger.debug("Unhandled phone event type: %s", event_type)
            return None

    def init_demo_call(
        self,
        caller_number: str,
        called_number: str,
        customer_id: str | None = None,
    ) -> str:
        """Initialise a demo CallState and return its call_connection_id."""
        call_id = f"demo-{caller_number[-8:] or 'anonymous'}"
        if call_id not in self._calls:
            self._calls[call_id] = CallState(
                call_connection_id=call_id,
                server_call_id=f"server-{call_id}",
                caller_number=caller_number,
                called_number=called_number,
                tenant_ctx=resolve_tenant_for_phone(called_number),
                audio_enabled=False,
                known_customer_id=customer_id,
            )
        return call_id

    async def process_demo_message(
        self,
        message: str,
        caller_number: str,
        called_number: str,
        call_connection_id: str | None = None,
        customer_id: str | None = None,
    ) -> dict:
        """Process a text turn as if it were a phone speech recognition result.

        This keeps the phone channel usable before an ACS phone number is
        acquired: tests and demos can inject the recognized text directly while
        exercising the same session and orchestrator path as real calls.
        """
        call_id = call_connection_id or f"demo-{caller_number[-8:] or 'anonymous'}"
        state = self._calls.get(call_id)
        if not state:
            state = CallState(
                call_connection_id=call_id,
                server_call_id=f"server-{call_id}",
                caller_number=caller_number,
                called_number=called_number,
                tenant_ctx=resolve_tenant_for_phone(called_number),
                audio_enabled=False,
                known_customer_id=customer_id,
            )
            self._calls[call_id] = state

        result = await self._handle_recognize_completed(
            {
                "type": "Microsoft.Communication.RecognizeCompleted",
                "data": {
                    "callConnectionId": call_id,
                    "speechResult": {"speech": message},
                },
            }
        )
        result["demo_mode"] = True
        result["call_connection_id"] = call_id
        return result

    async def disconnect_demo_call(self, call_connection_id: str) -> dict | None:
        return await self._handle_call_disconnected(
            {
                "type": "Microsoft.Communication.CallDisconnected",
                "data": {"callConnectionId": call_connection_id},
            }
        )

    async def _handle_incoming_call(self, event: dict) -> dict:
        data = event.get("data", {})
        incoming_call_context = data.get("incomingCallContext", "")
        server_call_id = data.get("serverCallId", "")

        from_info = data.get("from", {})
        to_info = data.get("to", {})
        caller_number = from_info.get("phoneNumber", {}).get("value", "") or from_info.get("rawId", "")
        called_number = to_info.get("phoneNumber", {}).get("value", "") or to_info.get("rawId", "")

        logger.info("Incoming call from %s to %s", caller_number, called_number)

        tenant_ctx = resolve_tenant_for_phone(called_number)
        acs_conn = tenant_ctx.config.acs_connection_string
        if not acs_conn:
            logger.error(
                "ACS connection string not configured for tenant %s",
                tenant_ctx.tenant_id,
            )
            return {"error": "acs_not_configured"}

        client = self._get_acs_client(acs_conn)
        callback_uri = f"{self._callback_base_url}/api/phone-webhook"

        answer_result = client.answer_call(
            incoming_call_context=incoming_call_context,
            callback_url=callback_uri,
            cognitive_services_endpoint=self._speech_endpoint,
        )

        call_connection_id = answer_result.call_connection.call_connection_id

        state = CallState(
            call_connection_id=call_connection_id,
            server_call_id=server_call_id,
            caller_number=caller_number,
            called_number=called_number,
            tenant_ctx=tenant_ctx,
        )
        self._calls[call_connection_id] = state

        logger.info(
            "Answered call %s from %s (tenant %s)",
            call_connection_id,
            caller_number,
            tenant_ctx.tenant_id,
        )
        return {"call_connection_id": call_connection_id, "status": "answered"}

    async def _handle_call_connected(self, event: dict) -> dict | None:
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        state = self._calls.get(call_connection_id)
        if not state:
            logger.warning("CallConnected for unknown call: %s", call_connection_id)
            return None

        logger.info("Call connected: %s, playing greeting", call_connection_id)
        await self._play_tts(state, GREETING_MESSAGE)
        return {"call_connection_id": call_connection_id, "status": "greeting_played"}

    async def _handle_recognize_completed(self, event: dict) -> dict:
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        state = self._calls.get(call_connection_id)
        if not state:
            logger.warning("RecognizeCompleted for unknown call: %s", call_connection_id)
            return {"error": "unknown_call"}

        speech_result = data.get("speechResult", {})
        transcribed_text = speech_result.get("speech", "").strip()

        if not transcribed_text:
            logger.info("Empty speech result for call %s", call_connection_id)
            await self._play_tts(state, RETRY_MESSAGE)
            return {"call_connection_id": call_connection_id, "status": "empty_speech"}

        state.turn_count += 1
        state.transcript_parts.append(transcribed_text)
        logger.info(
            "Speech recognized (turn %d): %s",
            state.turn_count,
            transcribed_text[:200],
        )

        session = await self._ensure_session(state)
        state.session = session
        await self._save_call_message(state, "user", transcribed_text)
        conversation_history = await self._list_recent_history(state)

        known_customer_name = await self._resolve_customer_name(state)
        current_order = await self._resolve_current_order(state, session)
        if current_order:
            session.customer_id = current_order.customer_id
            session.current_order_id = current_order.id

        response_text_holder: list[str] = []

        async def capture_response(text: str) -> None:
            response_text_holder.append(text)

        orchestrator = OrderOrchestrator(
            tenant_ctx=state.tenant_ctx,
            azure_openai_endpoint=self._openai_endpoint,
            azure_openai_key=self._openai_key,
            deployment_name=self._openai_deployment_name,
        )

        try:
            result = await asyncio.wait_for(
                orchestrator.process_order_message(
                    message=transcribed_text,
                    line_user_id=state.caller_number,
                    reply_token=None,
                    source=OrderSource.PHONE,
                    response_callback=capture_response,
                    conversation_history=conversation_history,
                    pending_order_draft=session.pending_order_draft if session else None,
                    session_id=session.id if session else None,
                    known_customer_id=state.known_customer_id,
                    known_customer_name=known_customer_name,
                    current_order=current_order,
                ),
                timeout=self._phone_sync_ai_timeout_seconds,
            )
            if response_text_holder and not result.get("response"):
                result["response"] = response_text_holder[0]
        except TimeoutError:
            logger.warning(
                "Phone sync AI timed out for call %s after %.1fs",
                call_connection_id,
                self._phone_sync_ai_timeout_seconds,
            )
            await self._play_tts(state, PHONE_SYNC_FALLBACK_MESSAGE)
            await self._save_call_message(state, "assistant", PHONE_SYNC_FALLBACK_MESSAGE)
            state.order_confirmed = True
            return {
                "call_connection_id": call_connection_id,
                "status": "phone_sync_timeout",
                "response": PHONE_SYNC_FALLBACK_MESSAGE,
            }
        except Exception:
            logger.exception("Agent processing failed for call %s", call_connection_id)
            fallback_message = "ご注文を受け付けました。担当者が確認いたします。"
            await self._play_tts(state, fallback_message)
            await self._save_call_message(state, "assistant", fallback_message)
            state.order_confirmed = True
            return {"call_connection_id": call_connection_id, "error": "agent_failed"}

        order_id = result.get("order_id")
        if order_id:
            state.order_confirmed = True
            state.last_order_id = order_id

        session_repo = state.tenant_ctx.get_connector("ISessionRepository")
        if result.get("session_status") == "awaiting_reply":
            state.order_confirmed = False
            session.status = "awaiting_reply"
            session.pending_order_draft = result.get("pending_order_draft") or session.pending_order_draft
            session.pending_action_type = result.get("pending_action_type") or session.pending_action_type
            session.customer_id = result.get("customer_id") or session.customer_id
            session.current_order_id = result.get("current_order_id") or session.current_order_id
            session.current_order_snapshot = result.get("current_order_snapshot") or session.current_order_snapshot
            session.current_order_editable = result.get("current_order_editable", session.current_order_editable)
            session.expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TIMEOUT_HOURS)
            await session_repo.update_session(session)
        elif order_id:
            session.status = "completed"
            session.pending_order_draft = None
            session.pending_action_type = None
            session.customer_id = result.get("customer_id") or session.customer_id
            if result.get("current_order_cleared"):
                session.current_order_id = None
                session.current_order_snapshot = None
                session.current_order_editable = False
            else:
                session.current_order_id = result.get("current_order_id") or session.current_order_id
                session.current_order_snapshot = result.get("current_order_snapshot") or session.current_order_snapshot
                session.current_order_editable = result.get("current_order_editable", session.current_order_editable)
            await session_repo.update_session(session)

        response_text = result.get("response", "")
        if response_text:
            await self._play_tts(state, response_text)
            await self._save_call_message(state, "assistant", response_text)

        result["call_connection_id"] = call_connection_id
        result["status"] = "processed"
        return result

    async def _resolve_current_order(self, state: CallState, session: OrderSession) -> Order | None:
        customer_id = session.customer_id or state.known_customer_id
        if not customer_id:
            try:
                customer_repo = state.tenant_ctx.get_connector("ICustomerRepository")
                customer = await customer_repo.find_by_identifier(state.tenant_ctx.tenant_id, state.caller_number)
                if customer:
                    customer_id = customer.id
            except Exception:
                logger.warning("Failed to resolve customer for current_order lookup")

        if not customer_id:
            return None

        try:
            order_repo = state.tenant_ctx.get_connector("IOrderRepository")
            orders = await order_repo.list_by_customer(customer_id, limit=10)
            return _pick_current_order(orders)
        except Exception:
            logger.warning("Failed to load current order for call %s", state.call_connection_id)
            return None

    async def _resolve_customer_name(self, state: CallState) -> str | None:
        if not state.known_customer_id:
            return None
        try:
            repo = state.tenant_ctx.get_connector("ICustomerRepository")
            customer = await repo.get_by_id(state.tenant_ctx.tenant_id, state.known_customer_id)
            return customer.name if customer else None
        except Exception:
            logger.warning("Failed to resolve customer name for %s", state.known_customer_id)
            return None

    async def _handle_recognize_failed(self, event: dict) -> dict | None:
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        state = self._calls.get(call_connection_id)
        if not state:
            return None

        result_info = data.get("resultInformation", {})
        logger.warning(
            "RecognizeFailed for call %s: code=%s, message=%s",
            call_connection_id,
            result_info.get("subCode"),
            result_info.get("message"),
        )

        if state.turn_count >= MAX_TURNS:
            await self._play_tts(state, GOODBYE_MESSAGE)
            state.order_confirmed = True
            return {
                "call_connection_id": call_connection_id,
                "status": "max_turns_reached",
            }

        await self._play_tts(state, RETRY_MESSAGE)
        return {"call_connection_id": call_connection_id, "status": "retry"}

    async def _handle_play_completed(self, event: dict) -> dict | None:
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        state = self._calls.get(call_connection_id)
        if not state:
            return None

        if state.order_confirmed or state.turn_count >= MAX_TURNS:
            logger.info("Call %s: order confirmed or max turns, hanging up", call_connection_id)
            await self._hangup(state)
            return {"call_connection_id": call_connection_id, "status": "hangup"}

        logger.info(
            "Call %s: starting next recognize (turn %d)",
            call_connection_id,
            state.turn_count + 1,
        )
        await self._start_recognize(state)
        return {"call_connection_id": call_connection_id, "status": "recognizing"}

    async def _handle_play_failed(self, event: dict) -> dict | None:
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        logger.error(
            "PlayFailed for call %s: %s",
            call_connection_id,
            data.get("resultInformation"),
        )
        state = self._calls.get(call_connection_id)
        if state:
            await self._hangup(state)
        return {"call_connection_id": call_connection_id, "status": "play_failed"}

    async def _handle_call_disconnected(self, event: dict) -> dict | None:
        data = event.get("data", {})
        call_connection_id = data.get("callConnectionId", "")
        state = self._calls.pop(call_connection_id, None)
        if not state:
            logger.debug("CallDisconnected for unknown call: %s", call_connection_id)
            return None

        logger.info(
            "Call disconnected: %s, turns=%d, order_id=%s",
            call_connection_id,
            state.turn_count,
            state.last_order_id,
        )

        if state.session:
            session_repo = state.tenant_ctx.get_connector("ISessionRepository")
            state.session.status = "completed"
            await session_repo.update_session(state.session)

        return {
            "call_connection_id": call_connection_id,
            "status": "disconnected",
            "turns": state.turn_count,
        }

    async def _start_recognize(self, state: CallState) -> None:
        if not state.audio_enabled:
            return
        acs_conn = state.tenant_ctx.config.acs_connection_string
        if not acs_conn:
            return
        client = self._get_acs_client(acs_conn)
        call_connection = client.get_call_connection(state.call_connection_id)

        target = PhoneNumberIdentifier(state.caller_number)
        call_connection.start_recognizing_media(
            input_type="speech",
            target_participant=target,
            speech_language="ja-JP",
            end_silence_timeout_in_seconds=5,
        )

    async def _play_tts(self, state: CallState, text: str) -> None:
        if not state.audio_enabled:
            logger.info("Demo phone call %s response: %s", state.call_connection_id, text)
            return
        acs_conn = state.tenant_ctx.config.acs_connection_string
        if not acs_conn:
            return
        client = self._get_acs_client(acs_conn)
        call_connection = client.get_call_connection(state.call_connection_id)

        play_source = TextSource(text=text, voice_name=TTS_VOICE)
        call_connection.play_media(
            play_source=play_source,
            play_to=[PhoneNumberIdentifier(state.caller_number)],
        )
        logger.info("Playing TTS (%d chars) on call %s", len(text), state.call_connection_id)

    async def _hangup(self, state: CallState) -> None:
        if not state.audio_enabled:
            return
        acs_conn = state.tenant_ctx.config.acs_connection_string
        if not acs_conn:
            return
        client = self._get_acs_client(acs_conn)
        call_connection = client.get_call_connection(state.call_connection_id)

        try:
            call_connection.hang_up(is_for_everyone=True)
            logger.info("Hung up call %s", state.call_connection_id)
        except Exception:
            logger.exception("Failed to hang up call %s", state.call_connection_id)

    async def _save_call_message(self, state: CallState, role: str, text: str) -> None:
        session = state.session
        if not session or not text:
            return
        history_repo = get_message_history_repo(state.tenant_ctx)
        await save_message(
            history_repo,
            MessageHistory(
                id=build_message_history_id(role, session.id, f"{state.call_connection_id}-{state.turn_count}"),
                tenant_id=state.tenant_ctx.tenant_id,
                session_id=session.id,
                channel="phone",
                channel_user_id=state.caller_number,
                role=role,
                text=text,
            ),
        )

    async def _list_recent_history(self, state: CallState) -> list[MessageHistory]:
        history_repo = get_message_history_repo(state.tenant_ctx)
        if history_repo is None:
            return []
        try:
            return await history_repo.list_recent_messages(
                state.tenant_ctx.tenant_id,
                "phone",
                state.caller_number,
                HISTORY_CONTEXT_LIMIT,
            )
        except Exception:
            logger.exception("Failed to load phone message history; continuing without memory")
            return []

    async def _ensure_session(self, state: CallState) -> OrderSession:
        session_repo = state.tenant_ctx.get_connector("ISessionRepository")

        async with get_channel_user_lock("phone", state.caller_number):
            session = await session_repo.find_active_session(state.tenant_ctx.tenant_id, "phone", state.caller_number)
            if session:
                session.last_message_at = datetime.now(timezone.utc)
                await session_repo.update_session(session)
                return session

            session = OrderSession(
                id=f"sess-phone-{state.caller_number[-8:]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                tenant_id=state.tenant_ctx.tenant_id,
                channel="phone",
                channel_user_id=state.caller_number,
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TIMEOUT_HOURS),
            )
            return await session_repo.create_session(session)


def _pick_current_order(orders: list[Order]) -> Order | None:
    open_statuses = {OrderStatus.ACCEPTED, OrderStatus.SHIPPING}
    candidates = [order for order in orders if order.status in open_statuses]
    if not candidates:
        return None
    return sorted(candidates, key=lambda order: order.updated_at, reverse=True)[0]
