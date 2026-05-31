"""
受注ステータス自動更新サービス
- 30分ごとに実行
- ACCEPTED かつ注文確定から10分以上経過 → SHIPPING に変更
- SHIPPING かつ配送日が今日以前 かつ時間条件を満たす → COMPLETED に変更
  - 時間指定なし: 12:00 JST 以降
  - 時間指定あり: 指定時間帯の終了時刻以降
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.models.order import OrderStatus
from src.services.tenant_resolver import resolve_tenant_by_id

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
INTERVAL_SECONDS = 30 * 60  # 30分
SHIPPING_THRESHOLD_MINUTES = 10  # 受注確定から配送中に変えるまでの時間
DEFAULT_COMPLETE_HOUR = 12  # 時間指定なしの場合の完了判定時刻（JST）

# 時間帯指定 → 終了時刻のマッピング
TIME_SLOT_END_HOUR: dict[str, int] = {
    "午前中": 11,
    "12:00-14:00": 14,
    "14:00-16:00": 16,
    "16:00-18:00": 18,
    "18:00-20:00": 20,
}


def _parse_time_slot_end_hour(time_slot: str | None) -> int:
    """配送時間帯から終了時刻（時）を返す。不明な場合はデフォルト。"""
    if not time_slot:
        return DEFAULT_COMPLETE_HOUR
    return TIME_SLOT_END_HOUR.get(time_slot, DEFAULT_COMPLETE_HOUR)


async def _run_once(tenant_id: str) -> None:
    """1回分のステータス更新処理。"""
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc.astimezone(JST)
    today_jst = now_jst.date()

    try:
        ctx = resolve_tenant_by_id(tenant_id)
        repo = ctx.get_connector("IOrderRepository")
        orders = await repo.list_by_statuses(
            tenant_id,
            [OrderStatus.ACCEPTED.value, OrderStatus.SHIPPING.value],
        )
    except Exception:
        logger.exception("Failed to fetch orders for status update (tenant=%s)", tenant_id)
        return

    shipping_count = 0
    completed_count = 0

    for order in orders:
        try:
            # ACCEPTED → SHIPPING: 注文確定から10分以上経過
            if order.status == OrderStatus.ACCEPTED:
                updated_at = order.updated_at
                if updated_at:
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    elapsed = (now_utc - updated_at).total_seconds() / 60
                    if elapsed >= SHIPPING_THRESHOLD_MINUTES:
                        await repo.update_status(tenant_id, order.id, OrderStatus.SHIPPING)
                        logger.info(
                            "Status ACCEPTED→SHIPPING: order=%s (elapsed=%.1fmin)",
                            order.id,
                            elapsed,
                        )
                        shipping_count += 1

            # SHIPPING → COMPLETED: 配送日が今日以前かつ時間条件を満たす
            elif order.status == OrderStatus.SHIPPING:
                delivery_date = order.delivery_date
                if delivery_date and delivery_date <= today_jst:
                    end_hour = _parse_time_slot_end_hour(order.delivery_time_slot)
                    if now_jst.hour >= end_hour:
                        await repo.update_status(tenant_id, order.id, OrderStatus.COMPLETED)
                        logger.info(
                            "Status SHIPPING→COMPLETED: order=%s (delivery=%s, slot=%s, hour=%d)",
                            order.id,
                            delivery_date,
                            order.delivery_time_slot,
                            now_jst.hour,
                        )
                        completed_count += 1

        except Exception:
            logger.exception("Failed to update status for order=%s", order.id)

    if shipping_count or completed_count:
        logger.info(
            "Status update done (tenant=%s): SHIPPING+%d, COMPLETED+%d",
            tenant_id,
            shipping_count,
            completed_count,
        )


def _seconds_until_next_slot() -> float:
    """JST 0:00 起点で30分刻みの次の実行時刻までの秒数を返す。
    例: 現在 0:10 → 次は 0:30 → 待ち 20分
        現在 0:30 → 次は 1:00 → 待ち 30分
        現在 0:00 → 次は 0:30 → 待ち 30分
    """
    now_jst = datetime.now(JST)
    elapsed_seconds = now_jst.hour * 3600 + now_jst.minute * 60 + now_jst.second
    remainder = elapsed_seconds % INTERVAL_SECONDS
    wait = INTERVAL_SECONDS - remainder if remainder > 0 else INTERVAL_SECONDS
    return float(wait)


async def run_order_status_updater(tenant_ids: list[str]) -> None:
    """JST 0:00 起点で30分ごとにステータス更新を実行するループ。"""
    wait = _seconds_until_next_slot()
    logger.info(
        "Order status updater started: next run in %.0fs (at %s JST)",
        wait,
        (datetime.now(JST) + timedelta(seconds=wait)).strftime("%H:%M"),
    )
    while True:
        await asyncio.sleep(_seconds_until_next_slot())
        logger.info("Order status updater running at %s JST", datetime.now(JST).strftime("%H:%M"))
        for tenant_id in tenant_ids:
            await _run_once(tenant_id)
