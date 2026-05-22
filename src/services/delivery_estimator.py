"""配送日数推定サービス.

Created: 2026-05-22
Updated: 2026-05-22 21:11
"""

from __future__ import annotations

from datetime import date, timedelta

from src.models.order import DeliveryRoute

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


def estimate(route: DeliveryRoute | None, order_date: date | None = None) -> tuple[date, date]:
    """配送ルートから到着予定日の範囲を推定する."""
    base = order_date or date.today()
    min_days, max_days = _ROUTE_DELIVERY_DAYS.get(route, _DEFAULT_DELIVERY_DAYS) if route else _DEFAULT_DELIVERY_DAYS
    return base + timedelta(days=min_days), base + timedelta(days=max_days)


def format_estimate(min_date: date, max_date: date) -> str:
    """到着予定日を表示用文字列にフォーマットする."""
    if min_date == max_date:
        return f"{min_date.month}月{min_date.day}日頃のお届け予定"
    return f"{min_date.month}月{min_date.day}日〜{max_date.month}月{max_date.day}日頃のお届け予定"
