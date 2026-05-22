from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from src.models.order import TemperatureZone


class UnitType(StrEnum):
    KG = "kg"
    BOX = "箱"
    PIECE = "個"
    PACK = "パック"
    BUNCH = "房"
    BALL = "玉"
    CASE = "ケース"


class Product(BaseModel):
    id: str
    tenant_id: str
    name: str
    display_name: str | None = None
    category: str | None = None
    default_unit: UnitType
    temperature_zone: TemperatureZone
    unit_weight_kg: float | None = None
    is_variable_weight: bool = False
    price_per_unit: float | None = None
    origin: str | None = None
    appeal: str | None = None
    aliases: list[str] | None = None
    active: bool = True
