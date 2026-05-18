from __future__ import annotations

import aioodbc

from src.connectors.adapters._sql_util import to_odbc_dsn
from src.models.customer import Customer, CustomerDeliveryPreference
from src.models.order import DeliveryCarrier, DeliveryRoute
from src.models.tenant import ConnectorConfig


class SqlCustomerRepository:
    def __init__(self, config: ConnectorConfig):
        self._conn_str = to_odbc_dsn(config.connection or "")

    async def _get_connection(self):
        return await aioodbc.connect(dsn=self._conn_str)

    async def find_by_identifier(
        self, tenant_id: str, identifier: str
    ) -> Customer | None:
        query = """
        SELECT TOP 1 customer_id, tenant_id, name, short_name, line_user_id,
               email, phone, fax, default_route, default_carrier,
               default_time_slot, active
        FROM customers
        WHERE tenant_id = ? AND active = 1
          AND (line_user_id = ? OR phone = ? OR email = ? OR name LIKE ?)
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (tenant_id, identifier, identifier, identifier, f"%{identifier}%"),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                return _row_to_customer(row)

    async def find_by_line_user_id(
        self, tenant_id: str, line_user_id: str
    ) -> Customer | None:
        query = """
        SELECT customer_id, tenant_id, name, short_name, line_user_id,
               email, phone, fax, default_route, default_carrier,
               default_time_slot, active
        FROM customers
        WHERE tenant_id = ? AND line_user_id = ? AND active = 1
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id, line_user_id))
                row = await cur.fetchone()
                if not row:
                    return None
                return _row_to_customer(row)

    async def get_by_id(self, tenant_id: str, customer_id: str) -> Customer | None:
        query = """
        SELECT customer_id, tenant_id, name, short_name, line_user_id,
               email, phone, fax, default_route, default_carrier,
               default_time_slot, active
        FROM customers WHERE tenant_id = ? AND customer_id = ?
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id, customer_id))
                row = await cur.fetchone()
                if not row:
                    return None
                return _row_to_customer(row)

    async def list_all(self, tenant_id: str) -> list[Customer]:
        query = """
        SELECT customer_id, tenant_id, name, short_name, line_user_id,
               email, phone, fax, default_route, default_carrier,
               default_time_slot, active
        FROM customers WHERE tenant_id = ?
        ORDER BY customer_id
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id,))
                rows = await cur.fetchall()
                return [_row_to_customer(r) for r in rows]

    async def update(self, tenant_id: str, customer_id: str, fields: dict) -> Customer:
        allowed = {
            "name",
            "short_name",
            "line_user_id",
            "email",
            "phone",
            "fax",
            "active",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            existing = await self.get_by_id(tenant_id, customer_id)
            if not existing:
                raise ValueError(f"顧客ID「{customer_id}」が見つかりません。")
            return existing

        set_clause = ", ".join(f"{col} = ?" for col in updates)
        values = list(updates.values()) + [tenant_id, customer_id]
        query = (
            f"UPDATE customers SET {set_clause} WHERE tenant_id = ? AND customer_id = ?"
        )

        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, values)
                await conn.commit()

        updated = await self.get_by_id(tenant_id, customer_id)
        if not updated:
            raise ValueError(
                f"顧客ID「{customer_id}」の更新後データの取得に失敗しました。"
            )
        return updated


def _row_to_customer(row) -> Customer:
    pref = CustomerDeliveryPreference(
        default_route=DeliveryRoute(row[8]) if row[8] else None,
        default_carrier=DeliveryCarrier(row[9]) if row[9] else None,
        default_time_slot=row[10],
    )
    return Customer(
        id=row[0],
        tenant_id=row[1],
        name=row[2],
        short_name=row[3],
        line_user_id=row[4],
        email=row[5],
        phone=row[6],
        fax=row[7],
        delivery_preference=pref,
        active=bool(row[11]),
    )
