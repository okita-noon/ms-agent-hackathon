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
from src.models.order import OrderSource
from src.models.session import OrderSession
from src.services.channel_locks import get_channel_user_lock
from src.services.tenant_resolver import resolve_tenant_for_phone

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2
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
        self._phone_sync_ai_enabled = os.getenv("PHONE_SYNC_AI_ENABLED", "true").lower() == "true"
        self._phone_background_validation_enabled = (
            os.getenv("PHONE_BACKGROUND_VALIDATION_ENABLED", "true").lower() == "true"
        )
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

    async def process_demo_message(
        self,
        message: str,
        caller_number: str,
        called_number: str,
        call_connection_id: str | None = None,
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

        orchestrator = OrderOrchestrator(
            tenant_ctx=state.tenant_ctx,
            azure_openai_endpoint=self._openai_endpoint,
            azure_openai_key=self._openai_key,
            deployment_name=self._openai_deployment_name,
        )

        try:
            if self._phone_sync_ai_enabled:
                result = await asyncio.wait_for(
                    orchestrator.process_phone_order_with_inventory(
                        message=transcribed_text,
                        caller_number=state.caller_number,
                        pending_order_draft=session.pending_order_draft if session else None,
                    ),
                    timeout=self._phone_sync_ai_timeout_seconds,
                )
                if self._phone_background_validation_enabled and result.get("order_accepted"):
                    asyncio.create_task(
                        self._process_phone_order_background(
                            state=state,
                            message=transcribed_text,
                            pending_order_draft=session.pending_order_draft if session else None,
                        )
                    )
            else:
                result = await self._process_phone_order_full_sync(orchestrator, state, transcribed_text, session)
        except TimeoutError:
            logger.warning(
                "Phone sync AI timed out for call %s after %.1fs",
                call_connection_id,
                self._phone_sync_ai_timeout_seconds,
            )
            if self._phone_background_validation_enabled:
                asyncio.create_task(
                    self._process_phone_order_background(
                        state=state,
                        message=transcribed_text,
                        pending_order_draft=session.pending_order_draft if session else None,
                    )
                )
            await self._play_tts(state, PHONE_SYNC_FALLBACK_MESSAGE)
            state.order_confirmed = True
            return {
                "call_connection_id": call_connection_id,
                "status": "phone_sync_timeout",
                "response": PHONE_SYNC_FALLBACK_MESSAGE,
            }
        except Exception:
            logger.exception("Agent processing failed for call %s", call_connection_id)
            await self._play_tts(state, "ご注文を受け付けました。担当者が確認いたします。")
            state.order_confirmed = True
            return {"call_connection_id": call_connection_id, "error": "agent_failed"}

        order_id = result.get("order_id")
        if order_id or result.get("order_accepted"):
            state.order_confirmed = True
            state.last_order_id = order_id

        if result.get("session_status") == "awaiting_reply":
            state.order_confirmed = False
            session.status = "awaiting_reply"
            session.pending_order_draft = result.get("pending_order_draft") or session.pending_order_draft
            await state.tenant_ctx.get_connector("ISessionRepository").update_session(session)

        response_text = result.get("response", "")
        if response_text:
            await self._play_tts(state, response_text)

        return {
            "call_connection_id": call_connection_id,
            "status": "processed",
            "order_id": order_id,
            "response": response_text,
            "session_status": result.get("session_status"),
            "phone_sync_status": result.get("phone_sync_status"),
        }

    async def _process_phone_order_full_sync(
        self,
        orchestrator: OrderOrchestrator,
        state: CallState,
        message: str,
        session: OrderSession,
    ) -> dict:
        response_text_holder: list[str] = []

        async def capture_response(text: str) -> None:
            response_text_holder.append(text)

        result = await orchestrator.process_order_message(
            message=message,
            line_user_id=state.caller_number,
            reply_token=None,
            source=OrderSource.PHONE,
            response_callback=capture_response,
            pending_order_draft=session.pending_order_draft,
            session_id=session.id,
        )
        if response_text_holder and not result.get("response"):
            result["response"] = response_text_holder[0]
        return result

    async def _process_phone_order_background(
        self,
        state: CallState,
        message: str,
        pending_order_draft: dict | None,
    ) -> None:
        try:
            orchestrator = OrderOrchestrator(
                tenant_ctx=state.tenant_ctx,
                azure_openai_endpoint=self._openai_endpoint,
                azure_openai_key=self._openai_key,
                deployment_name=self._openai_deployment_name,
            )

            async def ignore_customer_response(_: str) -> None:
                return None

            result = await orchestrator.process_order_message(
                message=message,
                line_user_id=state.caller_number,
                reply_token=None,
                source=OrderSource.PHONE,
                response_callback=ignore_customer_response,
                pending_order_draft=pending_order_draft,
                session_id=state.session.id if state.session else None,
            )
            if result.get("order_id"):
                state.last_order_id = result["order_id"]
            logger.info(
                "Background phone validation completed for call %s: %s",
                state.call_connection_id,
                result,
            )
        except Exception:
            logger.exception("Background phone validation failed for call %s", state.call_connection_id)

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
