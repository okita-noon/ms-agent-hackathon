from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from azure.cosmos.aio import CosmosClient

DEFAULT_SEED_FILE = Path("infra/seed/cosmos-orders-20260523-demo.json")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_orders(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON array.")

    orders: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Order #{index} must be an object.")
        order_id = item.get("id") or item.get("uid")
        if not order_id:
            raise ValueError(f"Order #{index} is missing id.")
        if not item.get("tenant_id"):
            raise ValueError(f"Order {order_id} is missing tenant_id.")
        item["id"] = order_id
        item["uid"] = order_id
        orders.append(item)
    return orders


async def _upsert_orders(connection: str, database: str, container_name: str, orders: list[dict[str, Any]]) -> None:
    async with CosmosClient.from_connection_string(connection) as client:
        container = client.get_database_client(database).get_container_client(container_name)
        for order in orders:
            await container.upsert_item(order)
            print(f"upserted {order['id']} {order['delivery_date']} {order['customer_name']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo orders into Cosmos DB.")
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED_FILE)
    parser.add_argument("--database", default="orders")
    parser.add_argument("--container", default="order-documents")
    parser.add_argument("--connection-env", default="COSMOS_CONNECTION_STRING")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    _load_dotenv(Path(".env"))
    orders = _load_orders(args.file)

    print(f"loaded {len(orders)} orders from {args.file}")
    if args.dry_run:
        dates = sorted({order["delivery_date"] for order in orders})
        print(f"delivery_dates: {', '.join(dates)}")
        return

    connection = os.environ.get(args.connection_env)
    if not connection:
        raise SystemExit(f"{args.connection_env} is not set.")

    asyncio.run(_upsert_orders(connection, args.database, args.container, orders))


if __name__ == "__main__":
    main()
