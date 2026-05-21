from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from src.models.order import DeliveryCarrier, DeliveryRoute


class DeliveryLeadTime(StrEnum):
    """顧客ごとの納品グループ（受注日から納品日までのリードタイム）."""

    SAME_DAY = "当日"
    NEXT_DAY = "翌日"
    ONE_DAY_GAP = "中1日"
    TWO_DAY_GAP = "中2日"


class CustomerDeliveryPreference(BaseModel):
    default_route: DeliveryRoute | None = None
    default_carrier: DeliveryCarrier | None = None
    default_time_slot: str | None = None


class Customer(BaseModel):
    id: str
    tenant_id: str
    name: str
    short_name: str | None = None
    line_user_id: str | None = None
    email: str | None = None
    phone: str | None = None
    fax: str | None = None
    delivery_preference: CustomerDeliveryPreference = Field(default_factory=CustomerDeliveryPreference)
    delivery_lead_time: DeliveryLeadTime | None = None
    active: bool = True
