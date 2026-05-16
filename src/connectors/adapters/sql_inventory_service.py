from __future__ import annotations

import aioodbc

from src.connectors.adapters._sql_util import to_odbc_dsn
from src.connectors.interfaces.inventory_service import (
    Alternative,
    InventoryStatus,
    ReservationResult,
)
from src.models.tenant import ConnectorConfig


class SqlInventoryService:
    def __init__(self, config: ConnectorConfig):
        self._conn_str = to_odbc_dsn(config.connection or "")

    async def _get_connection(self):
        return await aioodbc.connect(dsn=self._conn_str)

    async def check(self, tenant_id: str, product_id: str, required_qty: float) -> InventoryStatus:
        query = """
        SELECT i.quantity - i.reserved_qty AS available_qty, i.unit, p.name
        FROM inventory i
        JOIN products p ON i.product_id = p.product_id AND i.tenant_id = p.tenant_id
        WHERE i.tenant_id = ? AND i.product_id = ?
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id, product_id))
                row = await cur.fetchone()
                if not row:
                    return InventoryStatus(
                        product_id=product_id,
                        product_name="不明",
                        available_qty=0,
                        unit="",
                        is_sufficient=False,
                    )
                return InventoryStatus(
                    product_id=product_id,
                    product_name=row[2],
                    available_qty=float(row[0]),
                    unit=row[1],
                    is_sufficient=float(row[0]) >= required_qty,
                )

    async def find_alternatives(self, tenant_id: str, product_id: str, qty: float) -> list[Alternative]:
        query = """
        SELECT p.product_id, p.name, i.quantity - i.reserved_qty AS available_qty, i.unit
        FROM products p
        JOIN inventory i ON p.product_id = i.product_id AND p.tenant_id = i.tenant_id
        WHERE p.tenant_id = ? AND p.category = (
            SELECT category FROM products WHERE product_id = ? AND tenant_id = ?
        ) AND p.product_id != ? AND p.active = 1 AND (i.quantity - i.reserved_qty) >= ?
        ORDER BY available_qty DESC
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id, product_id, tenant_id, product_id, qty))
                rows = await cur.fetchall()
                return [
                    Alternative(
                        product_id=r[0],
                        product_name=r[1],
                        available_qty=float(r[2]),
                        unit=r[3],
                    )
                    for r in rows
                ]

    async def reserve(self, tenant_id: str, product_id: str, qty: float) -> ReservationResult:
        query = """
        UPDATE inventory SET reserved_qty = reserved_qty + ?
        WHERE tenant_id = ? AND product_id = ? AND (quantity - reserved_qty) >= ?
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (qty, tenant_id, product_id, qty))
                if cur.rowcount > 0:
                    await conn.commit()
                    return ReservationResult(product_id=product_id, reserved_qty=qty, success=True)
                return ReservationResult(
                    product_id=product_id,
                    reserved_qty=0,
                    success=False,
                    message="在庫不足",
                )
