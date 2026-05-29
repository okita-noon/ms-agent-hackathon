from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.phone_handler import (
    GOODBYE_MESSAGE,
    GREETING_MESSAGE,
    MAX_TURNS,
    PHONE_SYNC_FALLBACK_MESSAGE,
    RETRY_MESSAGE,
    CallState,
    PhoneCallHandler,
)


def _make_handler(sync_ai: bool = True) -> PhoneCallHandler:
    handler = PhoneCallHandler(
        callback_base_url="https://test.example.com",
        azure_openai_endpoint="https://test.openai.azure.com/",
        azure_openai_key="test-key",
        speech_service_key="test-speech-key",
        speech_service_endpoint="https://test.speech.azure.com/",
    )
    handler._phone_sync_ai_enabled = sync_ai
    handler._phone_background_validation_enabled = False
    return handler


def _make_incoming_call_event(
    caller: str = "+81312345678",
    called: str = "+81501234567",
) -> dict:
    return {
        "type": "Microsoft.Communication.IncomingCall",
        "data": {
            "from": {"phoneNumber": {"value": caller}},
            "to": {"phoneNumber": {"value": called}},
            "incomingCallContext": "mock-context",
            "serverCallId": "mock-server-call-id",
        },
    }


def _make_call_connected_event(call_connection_id: str = "conn-001") -> dict:
    return {
        "type": "Microsoft.Communication.CallConnected",
        "data": {"callConnectionId": call_connection_id},
    }


def _make_recognize_completed_event(
    call_connection_id: str = "conn-001",
    speech: str = "りんご10箱、バナナ20kg",
) -> dict:
    return {
        "type": "Microsoft.Communication.RecognizeCompleted",
        "data": {
            "callConnectionId": call_connection_id,
            "speechResult": {"speech": speech},
        },
    }


def _make_recognize_failed_event(call_connection_id: str = "conn-001") -> dict:
    return {
        "type": "Microsoft.Communication.RecognizeFailed",
        "data": {
            "callConnectionId": call_connection_id,
            "resultInformation": {"subCode": 8510, "message": "No speech detected"},
        },
    }


def _make_play_completed_event(call_connection_id: str = "conn-001") -> dict:
    return {
        "type": "Microsoft.Communication.PlayCompleted",
        "data": {"callConnectionId": call_connection_id},
    }


def _make_call_disconnected_event(call_connection_id: str = "conn-001") -> dict:
    return {
        "type": "Microsoft.Communication.CallDisconnected",
        "data": {"callConnectionId": call_connection_id},
    }


def _register_call_state(handler: PhoneCallHandler, mock_tenant_ctx, conn_id: str = "conn-001") -> CallState:
    state = CallState(
        call_connection_id=conn_id,
        server_call_id="mock-server-id",
        caller_number="+81312345678",
        called_number="+81501234567",
        tenant_ctx=mock_tenant_ctx,
    )
    handler._calls[conn_id] = state
    return state


class TestHandleIncomingCall:
    @pytest.mark.asyncio
    async def test_answers_call_and_creates_state(self, mock_tenant_ctx):
        handler = _make_handler()

        mock_call_connection = MagicMock()
        mock_call_connection.call_connection_id = "conn-001"
        mock_answer_result = MagicMock()
        mock_answer_result.call_connection.call_connection_id = "conn-001"

        mock_client = MagicMock()
        mock_client.answer_call.return_value = mock_answer_result

        with (
            patch(
                "src.services.phone_handler.resolve_tenant_for_phone",
                return_value=mock_tenant_ctx,
            ),
            patch.object(handler, "_get_acs_client", return_value=mock_client),
        ):
            result = await handler.handle_event(_make_incoming_call_event())

        assert result["status"] == "answered"
        assert result["call_connection_id"] == "conn-001"
        assert "conn-001" in handler._calls
        assert handler._calls["conn-001"].caller_number == "+81312345678"

    @pytest.mark.asyncio
    async def test_returns_error_when_acs_not_configured(self, mock_tenant_ctx):
        handler = _make_handler()
        mock_tenant_ctx.config.acs_connection_string = None

        with patch(
            "src.services.phone_handler.resolve_tenant_for_phone",
            return_value=mock_tenant_ctx,
        ):
            result = await handler.handle_event(_make_incoming_call_event())

        assert result["error"] == "acs_not_configured"


class TestHandleCallConnected:
    @pytest.mark.asyncio
    async def test_plays_greeting(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)

        with patch.object(handler, "_play_tts", new_callable=AsyncMock) as mock_play:
            result = await handler.handle_event(_make_call_connected_event())

        assert result["status"] == "greeting_played"
        mock_play.assert_called_once_with(state, GREETING_MESSAGE)

    @pytest.mark.asyncio
    async def test_ignores_unknown_call(self):
        handler = _make_handler()
        result = await handler.handle_event(_make_call_connected_event("unknown"))
        assert result is None


class TestHandleRecognizeCompleted:
    @pytest.mark.asyncio
    async def test_processes_speech_through_phone_sync_orchestrator(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.return_value = {
            "response": "りんご10箱、在庫は確認できました。",
            "order_accepted": True,
            "phone_sync_status": "inventory_checked",
        }

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock),
        ):
            result = await handler.handle_event(_make_recognize_completed_event(speech="りんご10箱"))

        assert result["status"] == "processed"
        assert result["phone_sync_status"] == "inventory_checked"
        assert result["response"] == "りんご10箱、在庫は確認できました。"
        assert state.turn_count == 1
        assert state.order_confirmed is True

        call_kwargs = mock_orchestrator.process_phone_order_with_inventory.call_args
        assert call_kwargs.kwargs["message"] == "りんご10箱"
        assert call_kwargs.kwargs["caller_number"] == "+81312345678"
        assert call_kwargs.kwargs["session_id"].startswith("sess-phone-")

    @pytest.mark.asyncio
    async def test_does_not_start_background_validation_when_sync_order_saved(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.return_value = {
            "response": "りんご10箱、在庫は確認できました。",
            "order_accepted": True,
            "order_id": "ORD-PHONE",
            "phone_sync_status": "inventory_checked",
        }

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_process_phone_order_background", new_callable=AsyncMock) as mock_background,
            patch.object(handler, "_play_tts", new_callable=AsyncMock),
        ):
            result = await handler.handle_event(_make_recognize_completed_event(speech="りんご10箱"))

        assert result["order_id"] == "ORD-PHONE"
        mock_background.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_session_on_first_turn(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.return_value = {"response": "OK", "order_accepted": True}

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock),
        ):
            await handler.handle_event(_make_recognize_completed_event())

        session_repo.create_session.assert_called_once()
        created_session = session_repo.create_session.call_args[0][0]
        assert created_session.channel == "phone"
        assert "+81312345678" in created_session.channel_user_id

    @pytest.mark.asyncio
    async def test_sends_fallback_on_agent_error(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.side_effect = RuntimeError("LLM down")

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock) as mock_play,
        ):
            result = await handler.handle_event(_make_recognize_completed_event())

        assert result["error"] == "agent_failed"
        mock_play.assert_called_once()
        assert "担当者が確認" in mock_play.call_args[0][1]

    @pytest.mark.asyncio
    async def test_saves_user_and_assistant_history(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.return_value = {
            "response": "りんご10箱、在庫は確認できました。",
            "order_accepted": True,
        }

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock),
        ):
            await handler.handle_event(_make_recognize_completed_event(speech="りんご10箱"))

        assert history_repo.create_message.call_count == 2
        saved = [c.args[0] for c in history_repo.create_message.call_args_list]
        assert [m.role for m in saved] == ["user", "assistant"]
        assert saved[0].channel == "phone"
        assert saved[0].text == "りんご10箱"
        assert "在庫は確認できました" in saved[1].text

    @pytest.mark.asyncio
    async def test_saves_fallback_history_on_timeout(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.side_effect = TimeoutError()

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock),
        ):
            result = await handler.handle_event(_make_recognize_completed_event(speech="りんご10箱"))

        assert result["status"] == "phone_sync_timeout"
        saved = [c.args[0] for c in history_repo.create_message.call_args_list]
        assert [m.role for m in saved] == ["user", "assistant"]
        assert saved[1].text == PHONE_SYNC_FALLBACK_MESSAGE

    @pytest.mark.asyncio
    async def test_saves_fallback_history_on_agent_error(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.side_effect = RuntimeError("LLM down")

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock),
        ):
            result = await handler.handle_event(_make_recognize_completed_event(speech="りんご10箱"))

        assert result["error"] == "agent_failed"
        saved = [c.args[0] for c in history_repo.create_message.call_args_list]
        assert [m.role for m in saved] == ["user", "assistant"]
        assert "担当者が確認" in saved[1].text

    @pytest.mark.asyncio
    async def test_retries_on_empty_speech(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        with patch.object(handler, "_play_tts", new_callable=AsyncMock) as mock_play:
            result = await handler.handle_event(_make_recognize_completed_event(speech=""))

        assert result["status"] == "empty_speech"
        mock_play.assert_called_once_with(handler._calls["conn-001"], RETRY_MESSAGE)


class TestHandlePlayCompleted:
    @pytest.mark.asyncio
    async def test_starts_next_recognize_when_not_confirmed(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)
        state.order_confirmed = False

        with patch.object(handler, "_start_recognize", new_callable=AsyncMock) as mock_rec:
            result = await handler.handle_event(_make_play_completed_event())

        assert result["status"] == "recognizing"
        mock_rec.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_hangs_up_when_confirmed(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)
        state.order_confirmed = True

        with patch.object(handler, "_hangup", new_callable=AsyncMock) as mock_hangup:
            result = await handler.handle_event(_make_play_completed_event())

        assert result["status"] == "hangup"
        mock_hangup.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_hangs_up_at_max_turns(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)
        state.turn_count = MAX_TURNS

        with patch.object(handler, "_hangup", new_callable=AsyncMock) as mock_hangup:
            result = await handler.handle_event(_make_play_completed_event())

        assert result["status"] == "hangup"
        mock_hangup.assert_called_once()


class TestHandleRecognizeFailed:
    @pytest.mark.asyncio
    async def test_retries_on_failure(self, mock_tenant_ctx):
        handler = _make_handler()
        _register_call_state(handler, mock_tenant_ctx)

        with patch.object(handler, "_play_tts", new_callable=AsyncMock) as mock_play:
            result = await handler.handle_event(_make_recognize_failed_event())

        assert result["status"] == "retry"
        mock_play.assert_called_once()
        assert RETRY_MESSAGE in mock_play.call_args[0][1]

    @pytest.mark.asyncio
    async def test_gives_up_at_max_turns(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)
        state.turn_count = MAX_TURNS

        with patch.object(handler, "_play_tts", new_callable=AsyncMock) as mock_play:
            result = await handler.handle_event(_make_recognize_failed_event())

        assert result["status"] == "max_turns_reached"
        assert GOODBYE_MESSAGE in mock_play.call_args[0][1]


class TestHandleCallDisconnected:
    @pytest.mark.asyncio
    async def test_cleans_up_state(self, mock_tenant_ctx):
        handler = _make_handler()
        state = _register_call_state(handler, mock_tenant_ctx)
        state.session = MagicMock()

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")

        result = await handler.handle_event(_make_call_disconnected_event())

        assert result["status"] == "disconnected"
        assert "conn-001" not in handler._calls
        session_repo.update_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_unknown_call(self):
        handler = _make_handler()
        result = await handler.handle_event(_make_call_disconnected_event("unknown"))
        assert result is None


class TestOrchestratorCallback:
    @pytest.mark.asyncio
    async def test_response_callback_captures_text(self, mock_tenant_ctx):
        """Verify the orchestrator uses response_callback instead of LINE send."""
        handler = _make_handler(sync_ai=False)
        _register_call_state(handler, mock_tenant_ctx)

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        captured_callback = None

        async def mock_process(**kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("response_callback")
            if captured_callback:
                await captured_callback("テスト応答")
            return {"response": "テスト応答", "order_id": "ORD-TEST"}

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_order_message.side_effect = mock_process

        with (
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_play_tts", new_callable=AsyncMock) as mock_play,
        ):
            await handler.handle_event(_make_recognize_completed_event())

        assert captured_callback is not None
        mock_play.assert_called()


class TestDemoPhoneMessage:
    @pytest.mark.asyncio
    async def test_processes_demo_message_without_audio_calls(self, mock_tenant_ctx):
        handler = _make_handler()

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_phone_order_with_inventory.return_value = {
            "response": "りんご10箱、在庫は確認できました。",
            "order_accepted": True,
            "phone_sync_status": "inventory_checked",
        }

        with (
            patch(
                "src.services.phone_handler.resolve_tenant_for_phone",
                return_value=mock_tenant_ctx,
            ),
            patch(
                "src.services.phone_handler.OrderOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch.object(handler, "_get_acs_client") as mock_client,
        ):
            result = await handler.process_demo_message(
                message="りんご10箱",
                caller_number="+81312345678",
                called_number="+81501234567",
            )

        assert result["demo_mode"] is True
        assert result["response"] == "りんご10箱、在庫は確認できました。"
        assert handler._calls[result["call_connection_id"]].audio_enabled is False
        mock_client.assert_not_called()
