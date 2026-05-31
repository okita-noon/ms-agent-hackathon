from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable


class OrderIntent(StrEnum):
    SMALL_TALK = "small_talk"
    NEW_ORDER = "new_order"
    MODIFY_CURRENT_ORDER = "modify_current_order"
    PARTIAL_CANCEL = "partial_cancel"
    FULL_CANCEL = "full_cancel"
    REPEAT_PREVIOUS_ORDER = "repeat_previous_order"
    REPEAT_USUAL_ORDER = "repeat_usual_order"
    INVENTORY_INQUIRY = "inventory_inquiry"
    ORDER_STATUS_INQUIRY = "order_status_inquiry"
    INSIST_ON_SHORTAGE = "insist_on_shortage"
    UNCLEAR = "unclear"


@dataclass(slots=True)
class IntentResult:
    intent: OrderIntent
    confidence: float = 1.0
    requires_confirmation: bool = False
    reason: str = ""


LLMClassifier = Callable[[str], Awaitable[str]]


class IntentUnderstandingService:
    """注文会話の意図分類。

    明確な高リスク操作は deterministic に分類し、ルールで拾えない表現は
    LLM classifier を注入して分類できる境界を用意する。
    """

    def __init__(self, llm_classifier: LLMClassifier | None = None):
        self._llm_classifier = llm_classifier

    async def classify(
        self,
        message: str,
        *,
        has_current_order: bool,
        has_pending_shortage: bool = False,
    ) -> IntentResult:
        rule_result = _classify_by_rule(
            message,
            has_current_order=has_current_order,
            has_pending_shortage=has_pending_shortage,
        )
        if rule_result:
            return rule_result

        if self._llm_classifier:
            classified = _parse_llm_intent(
                await self._llm_classifier(
                    _build_intent_prompt(
                        message,
                        has_current_order=has_current_order,
                        has_pending_shortage=has_pending_shortage,
                    )
                )
            )
            if classified:
                return classified

        return IntentResult(intent=OrderIntent.UNCLEAR, confidence=0.0)


def _classify_by_rule(
    message: str,
    *,
    has_current_order: bool,
    has_pending_shortage: bool = False,
) -> IntentResult | None:
    normalized = re.sub(r"\s+", "", message).lower()
    if not normalized:
        return IntentResult(intent=OrderIntent.SMALL_TALK, confidence=0.9, reason="empty message")

    if has_pending_shortage and _is_insist_on_shortage_by_rule(normalized):
        return IntentResult(
            intent=OrderIntent.INSIST_ON_SHORTAGE,
            confidence=0.9,
            reason="insistence keyword while shortage pending",
        )

    if _is_small_talk(normalized):
        return IntentResult(intent=OrderIntent.SMALL_TALK, confidence=0.9, reason="social conversation")

    if any(keyword in normalized for keyword in ("在庫", "ざいこ")) and not _has_order_request_keyword(normalized):
        return IntentResult(intent=OrderIntent.INVENTORY_INQUIRY, confidence=0.95)

    if any(keyword in normalized for keyword in ("今の注文", "現在の注文", "注文状況")):
        if _has_cancel_keyword(normalized):
            return IntentResult(intent=OrderIntent.FULL_CANCEL, confidence=0.95)
        return IntentResult(intent=OrderIntent.ORDER_STATUS_INQUIRY, confidence=0.95)

    if any(keyword in normalized for keyword in ("いつもの", "何時もの", "定番")):
        return IntentResult(intent=OrderIntent.REPEAT_USUAL_ORDER, confidence=0.95)

    if any(
        keyword in normalized for keyword in ("前と同じ", "前回と同じ", "前の注文と同じ", "この前と同じ")
    ) and not _has_cancel_keyword(normalized):
        return IntentResult(intent=OrderIntent.REPEAT_PREVIOUS_ORDER, confidence=0.95)

    if has_current_order and _is_full_cancel_by_rule(normalized):
        return IntentResult(intent=OrderIntent.FULL_CANCEL, confidence=0.95)

    if has_current_order and any(keyword in normalized for keyword in ("なしで", "外して", "抜いて")):
        return IntentResult(intent=OrderIntent.PARTIAL_CANCEL, confidence=0.85)

    if has_current_order and any(keyword in normalized for keyword in ("追加", "変更", "修正", "訂正", "増や", "減ら")):
        return IntentResult(intent=OrderIntent.MODIFY_CURRENT_ORDER, confidence=0.85)

    return None


def _parse_llm_intent(raw: str) -> IntentResult | None:
    try:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        data = json.loads(match.group(0) if match else raw)
        intent = OrderIntent(data.get("intent", "unclear"))
        confidence = float(data.get("confidence", 0.0))
        return IntentResult(
            intent=intent,
            confidence=confidence,
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            reason=str(data.get("reason", "")),
        )
    except Exception:
        return None


def _build_intent_prompt(
    message: str,
    *,
    has_current_order: bool,
    has_pending_shortage: bool = False,
) -> str:
    return (
        "次の食品卸の受注会話メッセージを intent JSON に分類してください。\n"
        "intent は small_talk, new_order, modify_current_order, partial_cancel, full_cancel, "
        "repeat_previous_order, repeat_usual_order, inventory_inquiry, order_status_inquiry, "
        "insist_on_shortage, unclear のいずれか。\n"
        "挨拶、天気の話、感謝だけなど、注文処理に入らない社交発話は small_talk としてください。\n"
        "現在注文が存在し、商品名と数量だけが送られている場合は、別注文の明示がない限り modify_current_order としてください。\n"
        "注文全体をやめる・取り消す意図は full_cancel、商品単位で外す意図は partial_cancel としてください。\n"
        "直前に在庫不足を通知済み（pending_shortage=true）の状態で、顧客が在庫超過の元数量を維持してでも手配を強く望む発話"
        "（例:『どうしてもこの数量で欲しい』『なんとかしてください』『無理してでも用意して』）は insist_on_shortage としてください。"
        "ただし『はい』『それでお願いします』など提示在庫数量への単なる承諾は insist_on_shortage ではありません。\n"
        f"current_order_exists={has_current_order}\n"
        f"pending_shortage={has_pending_shortage}\n"
        f"message={message}\n"
        '出力例: {"intent":"full_cancel","confidence":0.9,"requires_confirmation":false,"reason":"..."}'
    )


def is_rule_full_cancel(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message).lower()
    return _is_full_cancel_by_rule(normalized)


def _is_full_cancel_by_rule(normalized: str) -> bool:
    return any(
        keyword in normalized
        for keyword in (
            "全部キャンセル",
            "全てキャンセル",
            "すべてキャンセル",
            "注文キャンセル",
            "前の注文をキャンセル",
            "今の注文をキャンセル",
            "現在の注文をキャンセル",
            "キャンセルでお願いします",
            "全部なし",
            "今の注文なし",
            "現在の注文なし",
            "全キャンセル",
            "やっぱりやめます",
        )
    )


def _has_cancel_keyword(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ("キャンセル", "取消", "取り消", "なし", "やめ"))


def _is_insist_on_shortage_by_rule(normalized: str) -> bool:
    if _has_cancel_keyword(normalized):
        return False
    strong_phrases = (
        "どうしても",
        "どーしても",
        "なんとか",
        "何とか",
        "なんとかして",
        "至急",
        "緊急",
        "無理してでも",
        "無理を承知",
        "ないと困",
        "間に合わない",
        "間に合いません",
        "絶対必要",
        "絶対欲しい",
        "絶対にほしい",
        "全部欲しい",
        "全量欲しい",
        "元の数量",
        "元の量",
        "元の数",
    )
    if any(phrase in normalized for phrase in strong_phrases):
        return True
    moderate_phrases = (
        "急ぎで",
        "急ぎなので",
        "急ぎです",
        "必要なので",
        "必要です",
        "必要だから",
        "用意してください",
        "用意してほしい",
        "そろえてください",
        "揃えてください",
    )
    return any(phrase in normalized for phrase in moderate_phrases)


def _has_order_request_keyword(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ("ください", "下さい", "お願い", "納品", "届け"))


def _is_small_talk(normalized: str) -> bool:
    orderish_keywords = (
        "注文",
        "発注",
        "在庫",
        "納品",
        "配送",
        "届け",
        "ください",
        "下さい",
        "お願い",
        "キャンセル",
        "変更",
        "追加",
        "修正",
        "いつもの",
        "前と同じ",
        "前回と同じ",
    )
    if any(keyword in normalized for keyword in orderish_keywords):
        return False
    if re.search(r"\d", normalized):
        return False

    social_patterns = (
        "おはよう",
        "こんにちは",
        "こんばんは",
        "お世話になります",
        "お世話になっております",
        "いい天気",
        "良い天気",
        "天気いい",
        "天気がいい",
        "暑いですね",
        "寒いですね",
        "雨ですね",
        "晴れですね",
        "ありがとう",
        "ありがとうございます",
        "助かります",
        "よろしく",
    )
    return any(pattern in normalized for pattern in social_patterns)
