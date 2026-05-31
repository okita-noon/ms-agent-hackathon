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

    async def test_classifies_insist_on_shortage_when_shortage_pending(self):
        """在庫不足提示後、強要望キーワードを含む発話は insist_on_shortage に分類する。"""
        svc = IntentUnderstandingService()

        for message in (
            "どうしても10kg必要なので、なんとかお願いします",
            "急ぎなのでお願いします",
            "ないと困ります",
            "なんとかしてください",
            "至急用意してほしいです",
            "無理してでも欲しい",
        ):
            result = await svc.classify(message, has_current_order=False, has_pending_shortage=True)
            assert result.intent == OrderIntent.INSIST_ON_SHORTAGE, f"failed on: {message}"

    async def test_does_not_classify_as_insist_without_pending_shortage(self):
        """pending_shortage がない通常会話では強要望キーワードでも insist_on_shortage にしない。"""
        svc = IntentUnderstandingService()

        result = await svc.classify("どうしても5kg必要です", has_current_order=False, has_pending_shortage=False)

        assert result.intent != OrderIntent.INSIST_ON_SHORTAGE

    async def test_affirmative_short_reply_is_not_insist(self):
        """『お願いします』など単純な肯定返信は insist_on_shortage にしない。"""
        svc = IntentUnderstandingService()

        for message in ("はい", "お願いします", "それでお願いします"):
            result = await svc.classify(message, has_current_order=False, has_pending_shortage=True)
            assert result.intent != OrderIntent.INSIST_ON_SHORTAGE, f"misclassified affirmative: {message}"

    async def test_cancel_phrase_overrides_insist(self):
        """『やめます』などのキャンセル意図は強要望キーワードより優先する。"""
        svc = IntentUnderstandingService()

        result = await svc.classify("やっぱりやめます", has_current_order=True, has_pending_shortage=True)

        assert result.intent != OrderIntent.INSIST_ON_SHORTAGE
