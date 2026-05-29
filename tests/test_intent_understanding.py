from __future__ import annotations

from src.services.intent_understanding import IntentUnderstandingService, OrderIntent


class TestIntentUnderstandingService:
    async def test_classifies_natural_full_cancel_when_current_order_exists(self):
        svc = IntentUnderstandingService()

        for message in (
            "キャンセルでお願いします",
            "前の注文をキャンセルしてください",
            "やっぱりやめます",
            "今の注文なしでお願いします",
        ):
            result = await svc.classify(message, has_current_order=True)
            assert result.intent == OrderIntent.FULL_CANCEL

    async def test_classifies_memory_order_requests(self):
        svc = IntentUnderstandingService()

        assert (
            await svc.classify("いつものお願いします", has_current_order=False)
        ).intent == OrderIntent.REPEAT_USUAL_ORDER
        assert (
            await svc.classify("前と同じでお願いします", has_current_order=False)
        ).intent == OrderIntent.REPEAT_PREVIOUS_ORDER

    async def test_classifies_social_messages_as_small_talk(self):
        svc = IntentUnderstandingService()

        result = await svc.classify("今日はいい天気ですね", has_current_order=False)

        assert result.intent == OrderIntent.SMALL_TALK

    async def test_order_request_is_not_small_talk(self):
        svc = IntentUnderstandingService()

        result = await svc.classify("キウイ10個お願いします", has_current_order=False)

        assert result.intent != OrderIntent.SMALL_TALK

    async def test_uses_llm_classifier_when_rules_are_unclear(self):
        async def llm_classifier(prompt: str) -> str:
            assert "message=やめとこうかな" in prompt
            return '{"intent":"full_cancel","confidence":0.82,"requires_confirmation":false,"reason":"cancel intent"}'

        result = await IntentUnderstandingService(llm_classifier).classify(
            "やめとこうかな",
            has_current_order=True,
        )

        assert result.intent == OrderIntent.FULL_CANCEL
        assert result.confidence == 0.82
