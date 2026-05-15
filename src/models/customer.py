from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.order import DeliveryCarrier, DeliveryRoute


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
    delivery_preference: CustomerDeliveryPreference = Field(
        default_factory=CustomerDeliveryPreference
    )
    active: bool = True
