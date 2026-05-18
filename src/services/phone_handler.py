from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from azure.communication.callautomation import (
    CallAutomationClient,
    PhoneNumberIdentifier,
    TextSource,
)
from src.agents.orchestrator import DEFAULT_AZURE_OPENAI_DEPLOYMENT, OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.order import OrderSource
from src.models.session import OrderSession
from src.services.channel_locks import get_channel_user_lock
from src.services.learning_service import LearningService
from src.services.tenant_resolver import resolve_tenant_for_phone

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2
MAX_TURNS = 10
GREETING_MESSAGE = "お電話ありがとうございます。ご注文内容をお話しください。"
GOODBYE_MESSAGE = "ご注文ありがとうございました。失礼いたします。"
RETRY_MESSAGE = "すみません、聞き取れませんでした。もう一度お願いいたします。"
TTS_VOICE = "ja-JP-NanamiNeural"


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

        orchestrator = OrderOrchestrator(
            tenant_ctx=state.tenant_ctx,
            azure_openai_endpoint=self._openai_endpoint,
            azure_openai_key=self._openai_key,
            deployment_name=self._openai_deployment_name,
        )

        response_text_holder: list[str] = []

        async def capture_response(text: str) -> None:
            response_text_holder.append(text)

        try:
            result = await orchestrator.process_order_message(
                message=transcribed_text,
                line_user_id=state.caller_number,
                reply_token=None,
                source=OrderSource.PHONE,
                response_callback=capture_response,
                session_id=session.id if session else None,
            )
        except Exception:
            logger.exception("Agent processing failed for call %s", call_connection_id)
            await self._play_tts(state, "ご注文を受け付けました。担当者が確認いたします。")
            state.order_confirmed = True
            return {"call_connection_id": call_connection_id, "error": "agent_failed"}

        order_id = result.get("order_id")
        if order_id:
            state.order_confirmed = True
            state.last_order_id = order_id
            asyncio.create_task(
                self._run_learning(
                    tenant_ctx=state.tenant_ctx,
                    order_id=order_id,
                    user_id=state.caller_number,
                    original_message=transcribed_text,
                )
            )

        if result.get("session_status") == "awaiting_reply":
            state.order_confirmed = False

        response_text = response_text_holder[0] if response_text_holder else result.get("response", "")
        if response_text:
            await self._play_tts(state, response_text)

        return {
            "call_connection_id": call_connection_id,
            "status": "processed",
            "order_id": order_id,
        }

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

    async def _ensure_session(self, state: CallState) -> OrderSession:
        session_repo = state.tenant_ctx.get_connector("ISessionRepository")

        async with get_channel_user_lock("phone", state.caller_number):
            session = await session_repo.find_active_session(state.tenant_ctx.tenant_id, "phone", state.caller_number)
            if session:
                session.last_message_at = datetime.utcnow()
                await session_repo.update_session(session)
                return session

            session = OrderSession(
                id=f"sess-phone-{state.caller_number[-8:]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                tenant_id=state.tenant_ctx.tenant_id,
                channel="phone",
                channel_user_id=state.caller_number,
                status="active",
                expires_at=datetime.utcnow() + timedelta(hours=SESSION_TIMEOUT_HOURS),
            )
            return await session_repo.create_session(session)

    async def _run_learning(
        self,
        tenant_ctx: TenantContext,
        order_id: str,
        user_id: str,
        original_message: str,
    ) -> None:
        try:
            from src.models.intelligence import ResolvedItem

            order_repo = tenant_ctx.get_connector("IOrderRepository")
            customer_repo = tenant_ctx.get_connector("ICustomerRepository")

            order = await order_repo.find_by_id(tenant_ctx.tenant_id, order_id)
            if not order:
                return

            customer = await customer_repo.find_by_identifier(tenant_ctx.tenant_id, user_id)
            if not customer:
                return

            learning_service = LearningService(tenant_ctx)
            resolved_items = [
                ResolvedItem(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    qty=item.quantity,
                    unit=item.unit,
                )
                for item in order.items
            ]

            await learning_service.record_pattern(
                customer_id=customer.id,
                input_expression=original_message,
                resolved_items=resolved_items,
            )

            for item in order.items:
                await learning_service.update_customer_profile(
                    customer_id=customer.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit=item.unit,
                )

            logger.info("Learning completed for phone order %s", order_id)
        except Exception:
            logger.exception("Learning failed for phone order %s", order_id)
