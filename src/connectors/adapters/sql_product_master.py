from __future__ import annotations

import re
import unicodedata

import aioodbc

from src.connectors.adapters._sql_util import to_odbc_dsn
from src.models.order import TemperatureZone
from src.models.product import Product, UnitType
from src.models.tenant import ConnectorConfig


class SqlProductMaster:
    def __init__(self, config: ConnectorConfig):
        self._conn_str = to_odbc_dsn(config.connection or "")

    async def _get_connection(self):
        return await aioodbc.connect(dsn=self._conn_str)

    async def fuzzy_match(self, tenant_id: str, raw_name: str) -> Product | None:
        query = """
        SELECT TOP 1 p.product_id, p.tenant_id, p.name, p.display_name, p.category,
               p.default_unit, p.temperature_zone, p.unit_weight_kg,
               p.is_variable_weight, p.price_per_unit, p.active
        FROM products p
        LEFT JOIN product_aliases pa
          ON p.product_id = pa.product_id AND p.tenant_id = pa.tenant_id
        WHERE p.tenant_id = ? AND p.active = 1
          AND (p.name LIKE ? OR p.display_name LIKE ? OR pa.alias_name LIKE ?)
        ORDER BY
          CASE WHEN p.name = ? THEN 0
               WHEN pa.alias_name = ? THEN 1
               ELSE 2 END
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                for term in _search_terms(raw_name):
                    pattern = f"%{term}%"
                    await cur.execute(
                        query,
                        (tenant_id, pattern, pattern, pattern, term, term),
                    )
                    row = await cur.fetchone()
                    if row:
                        return _row_to_product(row)
                return None

    async def get_by_id(self, tenant_id: str, product_id: str) -> Product | None:
        query = """
        SELECT product_id, tenant_id, name, display_name, category,
               default_unit, temperature_zone, unit_weight_kg,
               is_variable_weight, price_per_unit, active
        FROM products WHERE tenant_id = ? AND product_id = ?
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id, product_id))
                row = await cur.fetchone()
                if not row:
                    return None
                return _row_to_product(row)

    async def list_all(self, tenant_id: str) -> list[Product]:
        query = """
        SELECT product_id, tenant_id, name, display_name, category,
               default_unit, temperature_zone, unit_weight_kg,
               is_variable_weight, price_per_unit, active
        FROM products WHERE tenant_id = ? AND active = 1
        ORDER BY name
        """
        async with await self._get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (tenant_id,))
                rows = await cur.fetchall()
                return [_row_to_product(r) for r in rows]


def _row_to_product(row) -> Product:
    return Product(
        id=row[0],
        tenant_id=row[1],
        name=row[2],
        display_name=row[3],
        category=row[4],
        default_unit=UnitType(row[5]) if row[5] else UnitType.KG,
        temperature_zone=TemperatureZone(row[6]) if row[6] else TemperatureZone.AMBIENT,
        unit_weight_kg=row[7],
        is_variable_weight=bool(row[8]),
        price_per_unit=row[9],
        active=bool(row[10]),
    )


def _search_terms(raw_name: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    if not normalized:
        return []

    terms = [normalized]
    stripped = re.sub(
        (
            r"[\s,、。:：;；]*\d+(?:\.\d+)?\s*"
            r"(?:kg|g|箱|個|パック|房|玉|ケース|袋|本|枚)?\s*$"
        ),
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    if stripped:
        terms.append(stripped)

    compact = re.sub(r"\s+", "", stripped or normalized)
    if compact:
        terms.append(compact)

    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped
