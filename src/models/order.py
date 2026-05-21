from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class OrderSource(StrEnum):
    LINE = "LINE"
    FAX = "FAX"
    WEB = "Web"
    EMAIL = "Email"
    PHONE = "Phone"
    MANUAL = "手入力"


class OrderStatus(StrEnum):
    PENDING = "未処理"
    NEEDS_REVIEW = "要対応"
    MANUFACTURING = "製造"
    SHIPPING = "配送"
    COMPLETED = "完了"
    CANCELLED = "キャンセル"
    AWAITING_REPLY = "返信待ち"


class TemperatureZone(StrEnum):
    AMBIENT = "常温"
    CHILLED = "冷蔵"
    FROZEN = "冷凍"


class DeliveryCarrier(StrEnum):
    OWN_FLEET = "自社便"
    ASHIKAWA = "芦川便"
    YAMATO_CHILLED = "冷蔵ヤマト便"
    YAMATO_FROZEN = "冷凍ヤマト便"


class DeliveryRoute(StrEnum):
    KITA_KANTO = "北関東便"
    NISHI_NIHON = "西日本便"
    CHUBU = "中部便"
    KYUSHU = "九州便"
    HOKKAIDO = "北海道便"
    TOHOKU = "東北便"
    KANTO = "関東便"
    KANSAI = "関西便"
    CHUGOKU = "中国便"
    SHIKOKU = "四国便"
    OKINAWA = "沖縄便"
    HOKURIKU = "北陸便"


class OrderItem(BaseModel):
    product_id: str
    product_name: str
    quantity: float | None = None
    unit: str
    temperature_zone: TemperatureZone
    unit_price: float | None = None
    is_variable_weight: bool = False
    actual_weight: float | None = None
    remarks: str | None = None


class Order(BaseModel):
    id: str = Field(alias="uid")
    tenant_id: str
    order_date: date
    preparation_date: date | None = None
    delivery_date: date | None = None
    customer_id: str
    customer_name: str
    source: OrderSource
    system: str | None = None
    items: list[OrderItem] = Field(default_factory=list)
    delivery_route: DeliveryRoute | None = None
    delivery_carrier: DeliveryCarrier | None = None
    delivery_time_slot: str | None = None
    yamato_tracking_number: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    remarks: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True}
