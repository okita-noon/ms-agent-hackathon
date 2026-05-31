"""
Daily demo data seeder.

Orders are generated relative to today (JST) so the dashboard always shows
fresh data during the hackathon review period.  IDs use the pattern
DAILY-YYYYMMDD-NNN, so each day's run safely overwrites via upsert.

Usage:
    python scripts/seed_demo_daily.py
    python scripts/seed_demo_daily.py --dry-run
    python scripts/seed_demo_daily.py --base-date 2026-06-10  # for testing
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from azure.cosmos.aio import CosmosClient

JST = timezone(timedelta(hours=9))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _ts(d: date, hour: int, minute: int) -> str:
    dt = datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=JST)
    return dt.isoformat()


def _build_orders(base: date) -> list[dict[str, Any]]:
    def day(offset: int) -> date:
        return base + timedelta(days=offset)

    def ds(offset: int) -> str:
        return day(offset).isoformat()

    def order_id(order_day: int, seq: int) -> str:
        return f"DAILY-{day(order_day).strftime('%Y%m%d')}-{seq:03d}"

    return [
        # ── day -4 : 完了済み ──────────────────────────────────────────
        {
            "id": order_id(-4, 1),
            "uid": order_id(-4, 1),
            "tenant_id": "T-001",
            "order_date": ds(-4),
            "preparation_date": ds(-4),
            "delivery_date": ds(-4),
            "customer_id": "C-004",
            "customer_name": "鮨処みなと",
            "source": "LINE",
            "system": "LINE",
            "items": [
                {"product_id": "P-001", "product_name": "りんご", "quantity": 6, "unit": "箱", "temperature_zone": "冷蔵", "is_variable_weight": False},
                {"product_id": "P-014", "product_name": "レモン", "quantity": 20, "unit": "個", "temperature_zone": "常温", "is_variable_weight": False},
            ],
            "delivery_route": "九州便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "午前",
            "status": "完了",
            "remarks": "青果売場向け",
            "session_id": f"sess-daily-{day(-4).strftime('%Y%m%d')}-001",
            "created_at": _ts(day(-4), 8, 10),
            "updated_at": _ts(day(-4), 17, 0),
        },
        {
            "id": order_id(-4, 2),
            "uid": order_id(-4, 2),
            "tenant_id": "T-001",
            "order_date": ds(-4),
            "preparation_date": ds(-4),
            "delivery_date": ds(-4),
            "customer_id": "C-009",
            "customer_name": "和食処こまち",
            "source": "Phone",
            "system": "Phone",
            "items": [
                {"product_id": "P-008", "product_name": "スイカ", "quantity": 12, "unit": "個", "temperature_zone": "常温", "is_variable_weight": False},
            ],
            "delivery_route": "中国便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "14:00",
            "status": "完了",
            "remarks": "電話確認済み",
            "session_id": f"sess-daily-{day(-4).strftime('%Y%m%d')}-002",
            "created_at": _ts(day(-4), 9, 35),
            "updated_at": _ts(day(-4), 17, 30),
        },
        # ── day -3 : 配送中 ────────────────────────────────────────────
        {
            "id": order_id(-3, 1),
            "uid": order_id(-3, 1),
            "tenant_id": "T-001",
            "order_date": ds(-3),
            "preparation_date": ds(-3),
            "delivery_date": ds(-3),
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
            "source": "Email",
            "system": "Email",
            "items": [
                {"product_id": "P-012", "product_name": "さくらんぼ", "quantity": 8, "unit": "パック", "temperature_zone": "冷蔵", "is_variable_weight": False},
                {"product_id": "P-017", "product_name": "ブルーベリー", "quantity": 2, "unit": "箱", "temperature_zone": "冷凍", "is_variable_weight": False},
            ],
            "delivery_route": "北関東便",
            "delivery_carrier": "冷蔵ヤマト便",
            "delivery_time_slot": "午後",
            "status": "配送中",
            "remarks": "冷蔵優先、ブルーベリーのみ冷凍別梱包",
            "created_at": _ts(day(-3), 10, 5),
            "updated_at": _ts(day(-3), 14, 20),
        },
        {
            "id": order_id(-3, 2),
            "uid": order_id(-3, 2),
            "tenant_id": "T-001",
            "order_date": ds(-3),
            "preparation_date": ds(-3),
            "delivery_date": ds(-2),
            "customer_id": "C-007",
            "customer_name": "イタリア食堂イルソーレ",
            "source": "Web",
            "system": "ECサイト",
            "items": [
                {"product_id": "P-002", "product_name": "バナナ", "quantity": 40, "unit": "kg", "temperature_zone": "常温", "is_variable_weight": False},
                {"product_id": "P-011", "product_name": "キウイ", "quantity": 30, "unit": "個", "temperature_zone": "常温", "is_variable_weight": False},
            ],
            "delivery_route": "関東便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "午前",
            "status": "受注済み",
            "remarks": None,
            "created_at": _ts(day(-3), 11, 15),
            "updated_at": _ts(day(-3), 11, 15),
        },
        # ── day -2 ─────────────────────────────────────────────────────
        {
            "id": order_id(-2, 1),
            "uid": order_id(-2, 1),
            "tenant_id": "T-001",
            "order_date": ds(-2),
            "preparation_date": ds(-2),
            "delivery_date": ds(-2),
            "customer_id": "C-002",
            "customer_name": "炭火焼鳥とり善",
            "source": "LINE",
            "system": "LINE",
            "items": [
                {"product_id": "P-003", "product_name": "みかん", "quantity": 60, "unit": "個", "temperature_zone": "冷凍", "is_variable_weight": False},
            ],
            "delivery_route": "西日本便",
            "delivery_carrier": "芦川便",
            "delivery_time_slot": "14:00",
            "status": "受注済み",
            "remarks": "普段の3倍。数量確認済み",
            "session_id": f"sess-daily-{day(-2).strftime('%Y%m%d')}-001",
            "created_at": _ts(day(-2), 9, 20),
            "updated_at": _ts(day(-2), 9, 25),
        },
        {
            "id": order_id(-2, 2),
            "uid": order_id(-2, 2),
            "tenant_id": "T-001",
            "order_date": ds(-2),
            "preparation_date": ds(-2),
            "delivery_date": ds(-1),
            "customer_id": "C-006",
            "customer_name": "中華食堂龍華",
            "source": "Phone",
            "system": "Phone",
            "items": [
                {"product_id": "P-006", "product_name": "いちご", "quantity": 20, "unit": "パック", "temperature_zone": "常温", "is_variable_weight": False},
                {"product_id": "P-009", "product_name": "なし", "quantity": 12, "unit": "個", "temperature_zone": "冷蔵", "is_variable_weight": False},
            ],
            "delivery_route": "東北便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "午前",
            "status": "配送中",
            "remarks": "朝便希望",
            "session_id": f"sess-daily-{day(-2).strftime('%Y%m%d')}-002",
            "created_at": _ts(day(-2), 10, 30),
            "updated_at": _ts(day(-2), 15, 0),
        },
        {
            "id": order_id(-2, 3),
            "uid": order_id(-2, 3),
            "tenant_id": "T-001",
            "order_date": ds(-2),
            "preparation_date": ds(-2),
            "delivery_date": ds(-1),
            "customer_id": "C-010",
            "customer_name": "ベーカリー麦の庭",
            "source": "Email",
            "system": "Email",
            "items": [
                {"product_id": "P-007", "product_name": "メロン", "quantity": 3, "unit": "玉", "temperature_zone": "冷凍", "is_variable_weight": False},
                {"product_id": "P-010", "product_name": "マンゴー", "quantity": 5, "unit": "個", "temperature_zone": "冷凍", "is_variable_weight": False},
            ],
            "delivery_route": "四国便",
            "delivery_carrier": "冷凍ヤマト便",
            "delivery_time_slot": "午後",
            "status": "配送中",
            "remarks": "冷凍まとめ便",
            "created_at": _ts(day(-2), 11, 10),
            "updated_at": _ts(day(-2), 16, 5),
        },
        # ── day -1 ─────────────────────────────────────────────────────
        {
            "id": order_id(-1, 1),
            "uid": order_id(-1, 1),
            "tenant_id": "T-001",
            "order_date": ds(-1),
            "preparation_date": ds(-1),
            "delivery_date": ds(-1),
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
            "source": "Web",
            "system": "ECサイト",
            "items": [
                {"product_id": "P-004", "product_name": "ぶどう", "quantity": 10, "unit": "房", "temperature_zone": "常温", "is_variable_weight": False},
                {"product_id": "P-015", "product_name": "アボカド", "quantity": 18, "unit": "個", "temperature_zone": "冷蔵", "is_variable_weight": False},
            ],
            "delivery_route": "北関東便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "午前",
            "status": "受注済み",
            "remarks": None,
            "created_at": _ts(day(-1), 9, 45),
            "updated_at": _ts(day(-1), 9, 45),
        },
        {
            "id": order_id(-1, 2),
            "uid": order_id(-1, 2),
            "tenant_id": "T-001",
            "order_date": ds(-1),
            "preparation_date": ds(-1),
            "delivery_date": ds(-1),
            "customer_id": "C-009",
            "customer_name": "和食処こまち",
            "source": "Phone",
            "system": "Phone",
            "items": [
                {"product_id": "P-002", "product_name": "バナナ", "quantity": 25, "unit": "kg", "temperature_zone": "常温", "is_variable_weight": False},
            ],
            "delivery_route": "中国便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "14:00",
            "status": "完了",
            "remarks": "電話確認済み",
            "session_id": f"sess-daily-{day(-1).strftime('%Y%m%d')}-002",
            "created_at": _ts(day(-1), 12, 45),
            "updated_at": _ts(day(-1), 17, 30),
        },
        {
            "id": order_id(-1, 3),
            "uid": order_id(-1, 3),
            "tenant_id": "T-001",
            "order_date": ds(-1),
            "preparation_date": ds(-1),
            "delivery_date": ds(1),
            "customer_id": "C-003",
            "customer_name": "洋食キッチンつばめ",
            "source": "LINE",
            "system": "LINE",
            "items": [
                {"product_id": "P-013", "product_name": "いちじく", "quantity": 30, "unit": "箱", "temperature_zone": "冷凍", "is_variable_weight": False},
            ],
            "delivery_route": "中部便",
            "delivery_carrier": "冷凍ヤマト便",
            "delivery_time_slot": "午前",
            "status": "要対応",
            "remarks": "在庫不足の可能性あり",
            "session_id": f"sess-daily-{day(-1).strftime('%Y%m%d')}-003",
            "created_at": _ts(day(-1), 11, 30),
            "updated_at": _ts(day(-1), 11, 31),
        },
        # ── day 0 (today) ──────────────────────────────────────────────
        {
            "id": order_id(0, 1),
            "uid": order_id(0, 1),
            "tenant_id": "T-001",
            "order_date": ds(0),
            "preparation_date": ds(0),
            "delivery_date": ds(0),
            "customer_id": "C-007",
            "customer_name": "イタリア食堂イルソーレ",
            "source": "Email",
            "system": "Email",
            "items": [
                {"product_id": "P-001", "product_name": "りんご", "quantity": 20, "unit": "箱", "temperature_zone": "冷蔵", "is_variable_weight": False},
            ],
            "delivery_route": "関東便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "午前",
            "status": "受注済み",
            "remarks": "販促用",
            "created_at": _ts(day(0), 8, 5),
            "updated_at": _ts(day(0), 8, 5),
        },
        {
            "id": order_id(0, 2),
            "uid": order_id(0, 2),
            "tenant_id": "T-001",
            "order_date": ds(0),
            "preparation_date": ds(0),
            "delivery_date": ds(1),
            "customer_id": "C-004",
            "customer_name": "鮨処みなと",
            "source": "LINE",
            "system": "LINE",
            "items": [
                {"product_id": "P-010", "product_name": "マンゴー", "quantity": 30, "unit": "個", "temperature_zone": "冷凍", "is_variable_weight": False},
                {"product_id": "P-017", "product_name": "ブルーベリー", "quantity": 6, "unit": "箱", "temperature_zone": "冷凍", "is_variable_weight": False},
            ],
            "delivery_route": "九州便",
            "delivery_carrier": "冷凍ヤマト便",
            "delivery_time_slot": "午後",
            "status": "要対応",
            "remarks": "冷凍在庫引当確認",
            "session_id": f"sess-daily-{day(0).strftime('%Y%m%d')}-002",
            "created_at": _ts(day(0), 10, 25),
            "updated_at": _ts(day(0), 10, 26),
        },
        {
            "id": order_id(0, 3),
            "uid": order_id(0, 3),
            "tenant_id": "T-001",
            "order_date": ds(0),
            "preparation_date": ds(0),
            "delivery_date": ds(0),
            "customer_id": "C-008",
            "customer_name": "レストラン花水木",
            "source": "Web",
            "system": "ECサイト",
            "items": [
                {"product_id": "P-007", "product_name": "メロン", "quantity": 4, "unit": "玉", "temperature_zone": "冷凍", "is_variable_weight": False},
            ],
            "delivery_route": "関西便",
            "delivery_carrier": "芦川便",
            "delivery_time_slot": "14:00",
            "status": "受注済み",
            "remarks": None,
            "created_at": _ts(day(0), 8, 15),
            "updated_at": _ts(day(0), 8, 15),
        },
        {
            "id": order_id(0, 4),
            "uid": order_id(0, 4),
            "tenant_id": "T-001",
            "order_date": ds(0),
            "preparation_date": ds(0),
            "delivery_date": ds(0),
            "customer_id": "C-010",
            "customer_name": "ベーカリー麦の庭",
            "source": "Phone",
            "system": "Phone",
            "items": [
                {"product_id": "P-015", "product_name": "アボカド", "quantity": 10, "unit": "個", "temperature_zone": "冷蔵", "is_variable_weight": False},
                {"product_id": "P-011", "product_name": "キウイ", "quantity": 24, "unit": "個", "temperature_zone": "常温", "is_variable_weight": False},
            ],
            "delivery_route": "四国便",
            "delivery_carrier": "自社便",
            "delivery_time_slot": "午前",
            "status": "受注済み",
            "remarks": "電話聞き取り",
            "session_id": f"sess-daily-{day(0).strftime('%Y%m%d')}-004",
            "created_at": _ts(day(0), 9, 15),
            "updated_at": _ts(day(0), 9, 16),
        },
        # ── day +1 (tomorrow delivery) ─────────────────────────────────
        {
            "id": order_id(0, 5),
            "uid": order_id(0, 5),
            "tenant_id": "T-001",
            "order_date": ds(0),
            "preparation_date": ds(0),
            "delivery_date": ds(2),
            "customer_id": "C-002",
            "customer_name": "炭火焼鳥とり善",
            "source": "Email",
            "system": "Email",
            "items": [
                {"product_id": "P-009", "product_name": "なし", "quantity": 20, "unit": "個", "temperature_zone": "冷蔵", "is_variable_weight": False},
                {"product_id": "P-012", "product_name": "さくらんぼ", "quantity": 12, "unit": "パック", "temperature_zone": "冷蔵", "is_variable_weight": False},
            ],
            "delivery_route": "西日本便",
            "delivery_carrier": "芦川便",
            "delivery_time_slot": "午後",
            "status": "受注済み",
            "remarks": "中1日配送",
            "created_at": _ts(day(0), 11, 10),
            "updated_at": _ts(day(0), 11, 40),
        },
        {
            "id": order_id(0, 6),
            "uid": order_id(0, 6),
            "tenant_id": "T-001",
            "order_date": ds(0),
            "preparation_date": ds(0),
            "delivery_date": ds(1),
            "customer_id": "C-005",
            "customer_name": "カフェ森ノ音",
            "source": "LINE",
            "system": "LINE",
            "items": [
                {"product_id": "P-008", "product_name": "スイカ", "quantity": 2, "unit": "個", "temperature_zone": "常温", "is_variable_weight": False},
                {"product_id": "P-004", "product_name": "ぶどう", "quantity": 5, "unit": "房", "temperature_zone": "常温", "is_variable_weight": False},
            ],
            "delivery_route": "北海道便",
            "delivery_carrier": "芦川便",
            "delivery_time_slot": "14:00",
            "status": "受注済み",
            "remarks": "ギフト包装",
            "session_id": f"sess-daily-{day(0).strftime('%Y%m%d')}-006",
            "created_at": _ts(day(0), 11, 25),
            "updated_at": _ts(day(0), 11, 26),
        },
    ]


async def _upsert_orders(connection: str, database: str, container_name: str, orders: list[dict[str, Any]]) -> None:
    async with CosmosClient.from_connection_string(connection) as client:
        container = client.get_database_client(database).get_container_client(container_name)
        for order in orders:
            await container.upsert_item(order)
            print(f"  upserted {order['id']:35s} delivery={order['delivery_date']} {order['status']:5s} {order['customer_name']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed daily demo orders into Cosmos DB.")
    parser.add_argument("--base-date", help="Override today (YYYY-MM-DD). Defaults to JST today.")
    parser.add_argument("--database", default="orders")
    parser.add_argument("--container", default="order-documents")
    parser.add_argument("--connection-env", default="COSMOS_CONNECTION_STRING")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    _load_dotenv(Path(".env"))

    if args.base_date:
        base = date.fromisoformat(args.base_date)
    else:
        base = datetime.now(JST).date()

    orders = _build_orders(base)
    print(f"base date (JST): {base}  orders to seed: {len(orders)}")

    if args.dry_run:
        for o in orders:
            print(f"  {o['id']:35s} delivery={o['delivery_date']} {o['status']:5s} {o['customer_name']}")
        return

    connection = os.environ.get(args.connection_env)
    if not connection:
        raise SystemExit(f"{args.connection_env} is not set.")

    asyncio.run(_upsert_orders(connection, args.database, args.container, orders))
    print("done.")


if __name__ == "__main__":
    main()
