from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from src.models.order import (
    DeliveryCarrier,
    DeliveryRoute,
    OrderStatus,
    TemperatureZone,
)


class PickingItem(BaseModel):
    uid: str
    order_uid: str
    delivery_date: date
    customer_name: str
    system: str | None = None
    unit_price: float | None = None
    temperature_zone: TemperatureZone
    product_name: str
    quantity: float | None = None
    unit: str | None = None
    delivery_route: DeliveryRoute | None = None
    delivery_carrier: DeliveryCarrier | None = None
    remarks: str | None = None
    delivery_time_slot: str | None = None
    yamato_tracking_number: str | None = None
    source: str | None = None
    status: OrderStatus = OrderStatus.ACCEPTED


class PickingList(BaseModel):
    date: date
    items: list[PickingItem] = Field(default_factory=list)

    @property
    def items_by_carrier(self) -> dict[DeliveryCarrier | None, list[PickingItem]]:
        groups: dict[DeliveryCarrier | None, list[PickingItem]] = {}
        for item in self.items:
            groups.setdefault(item.delivery_carrier, []).append(item)
        return groups
