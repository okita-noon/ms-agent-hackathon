"""配送日数推定サービス.

Created: 2026-05-22
Updated: 2026-05-24 01:03
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from src.models.customer import DeliveryLeadTime
from src.models.order import DeliveryRoute
from src.models.tenant import TenantConfig

# 配送ルート → (最短日数, 最長日数)。倉庫所在地は関東と仮定。
_ROUTE_DELIVERY_DAYS: dict[DeliveryRoute, tuple[int, int]] = {
    DeliveryRoute.KANTO: (1, 2),
    DeliveryRoute.KITA_KANTO: (1, 2),
    DeliveryRoute.TOHOKU: (2, 3),
    DeliveryRoute.CHUBU: (2, 3),
    DeliveryRoute.KANSAI: (2, 3),
    DeliveryRoute.HOKURIKU: (2, 3),
    DeliveryRoute.CHUGOKU: (3, 4),
    DeliveryRoute.SHIKOKU: (3, 4),
    DeliveryRoute.KYUSHU: (3, 4),
    DeliveryRoute.HOKKAIDO: (3, 5),
    DeliveryRoute.OKINAWA: (5, 7),
    DeliveryRoute.NISHI_NIHON: (2, 4),
}

_DEFAULT_DELIVERY_DAYS: tuple[int, int] = (2, 4)

_LEAD_TIME_DAYS: dict[DeliveryLeadTime, int] = {
    DeliveryLeadTime.SAME_DAY: 0,
    DeliveryLeadTime.NEXT_DAY: 1,
    DeliveryLeadTime.ONE_DAY_GAP: 2,
    DeliveryLeadTime.TWO_DAY_GAP: 3,
}


def _parse_extra_holidays(raw: list[str]) -> set[date]:
    """YYYY-MM-DD形式の文字列リストをdateのセットに変換する."""
    holidays: set[date] = set()
    for s in raw:
        try:
            holidays.add(date.fromisoformat(s))
        except ValueError:
            pass
    return holidays


def _is_closed(d: date, closed_weekdays: list[int], extra_holidays: set[date]) -> bool:
    """指定日が定休日かどうか判定する."""
    return d.weekday() in closed_weekdays or d in extra_holidays


def _advance_business_days(
    start: date,
    days: int,
    closed_weekdays: list[int],
    extra_holidays: set[date],
) -> date:
    """startからdays営業日後の日付を返す。days=0ならstart自体が営業日かチェックし、休みならスキップ."""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if not _is_closed(current, closed_weekdays, extra_holidays):
            remaining -= 1
    # days=0の場合でも、当日が休みなら次の営業日へ
    while _is_closed(current, closed_weekdays, extra_holidays):
        current += timedelta(days=1)
    return current


def estimate(
    route: DeliveryRoute | None,
    order_date: date | None = None,
    *,
    lead_time: DeliveryLeadTime | None = None,
    tenant_config: TenantConfig | None = None,
    now: datetime | None = None,
) -> tuple[date, date]:
    """到着予定日の範囲を推定する.

    lead_time が指定されていれば顧客固有のリードタイムを使用し、
    なければ配送ルートから推定する。
    tenant_config があれば締め時間と定休日を考慮する。
    """
    base = order_date or date.today()
    cutoff_hour = tenant_config.order_cutoff_hour if tenant_config else 16
    closed_weekdays = tenant_config.closed_weekdays if tenant_config else []
    extra_holidays = _parse_extra_holidays(tenant_config.extra_holidays) if tenant_config else set()

    # 締め時間判定: 過ぎていれば起算日を翌営業日にずらす
    current_time = now or datetime.now()
    if current_time.hour >= cutoff_hour:
        base = _advance_business_days(base, 1, closed_weekdays, extra_holidays)

    if lead_time is not None:
        days = _LEAD_TIME_DAYS.get(lead_time, 1)
        delivery = _advance_business_days(base, days, closed_weekdays, extra_holidays)
        return delivery, delivery

    min_days, _max_days = _ROUTE_DELIVERY_DAYS.get(route, _DEFAULT_DELIVERY_DAYS) if route else _DEFAULT_DELIVERY_DAYS
    delivery = _advance_business_days(base, min_days, closed_weekdays, extra_holidays)
    return delivery, delivery


def format_estimate(min_date: date, max_date: date) -> str:
    """到着予定日を表示用文字列にフォーマットする."""
    return f"{min_date.month}月{min_date.day}日配送予定"
