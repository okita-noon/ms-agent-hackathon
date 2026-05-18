from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class InventoryStatus(BaseModel):
    product_id: str
    product_name: str
    available_qty: float
    unit: str
    is_sufficient: bool = True


class Alternative(BaseModel):
    product_id: str
    product_name: str
    available_qty: float
    unit: str
    similarity_score: float = 0.0


class ReservationResult(BaseModel):
    product_id: str
    reserved_qty: float
    success: bool
    message: str = ""


class IInventoryService(Protocol):
    async def check(
        self, tenant_id: str, product_id: str, required_qty: float
    ) -> InventoryStatus: ...
    async def find_alternatives(
        self, tenant_id: str, product_id: str, qty: float
    ) -> list[Alternative]: ...
    async def reserve(
        self, tenant_id: str, product_id: str, qty: float
    ) -> ReservationResult: ...
