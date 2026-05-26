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
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _date_range_filter(field: str, start: date | None, end: date | None) -> tuple[str, list[dict[str, object]]]:
    where: list[str] = []
    params: list[dict[str, object]] = []
    if start:
        where.append(f"c.{field} >= @start")
        params.append({"name": "@start", "value": start.isoformat()})
    if end:
        where.append(f"c.{field} <= @end")
        params.append({"name": "@end", "value": end.isoformat()})
    return (" AND " + " AND ".join(where) if where else ""), params


def _build_patch(doc: dict[str, Any], *, adjust_same_day_fields: bool) -> dict[str, str] | None:
    created_at = _parse_datetime(doc.get("created_at"))
    if not created_at:
        return None

    order_date = _parse_date(doc.get("order_date"))
    corrected = created_at.astimezone(JST).date()
    if order_date == corrected:
        return None

    patch = {"order_date": corrected.isoformat()}
    old_order_date = order_date.isoformat() if order_date else None

    if adjust_same_day_fields and old_order_date:
        for field in ("delivery_date", "preparation_date"):
            if doc.get(field) == old_order_date:
                patch[field] = corrected.isoformat()

    return patch


async def _fix_order_dates(args: argparse.Namespace) -> int:
    connection = os.environ.get(args.connection_env)
    if not connection:
        raise SystemExit(f"{args.connection_env} is not set.")

    range_clause, range_params = _date_range_filter("created_at", args.created_from, args.created_to)
    query = (
        "SELECT * FROM c "
        "WHERE c.tenant_id = @tenant_id "
        "AND IS_DEFINED(c.created_at) "
        "AND IS_DEFINED(c.order_date)"
        f"{range_clause} "
        "ORDER BY c.created_at"
    )
    params = [{"name": "@tenant_id", "value": args.tenant_id}, *range_params]

    scanned = 0
    changed = 0
    async with CosmosClient.from_connection_string(connection) as client:
        container = client.get_database_client(args.database).get_container_client(args.container)
        items = container.query_items(query, parameters=params)
        async for doc in items:
            scanned += 1
            patch = _build_patch(doc, adjust_same_day_fields=not args.keep_delivery_dates)
            if not patch:
                continue

            changed += 1
            order_id = doc.get("id") or doc.get("uid")
            before = {
                "order_date": doc.get("order_date"),
                "delivery_date": doc.get("delivery_date"),
                "preparation_date": doc.get("preparation_date"),
            }
            after = {**before, **patch}
            print(f"{order_id}: {before} -> {after}")

            if args.apply:
                doc.update(patch)
                doc["updated_at"] = datetime.now(timezone.utc).isoformat()
                await container.replace_item(item=order_id, body=doc)

    mode = "applied" if args.apply else "dry-run"
    print(f"{mode}: scanned={scanned} changes={changed}")
    if not args.apply and changed:
        print("Run again with --apply to update Cosmos DB.")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix existing Cosmos DB order_date values that were saved using UTC instead of JST."
    )
    parser.add_argument("--tenant-id", default="T-001")
    parser.add_argument("--database", default="orders")
    parser.add_argument("--container", default="order-documents")
    parser.add_argument("--connection-env", default="COSMOS_CONNECTION_STRING")
    parser.add_argument("--created-from", type=date.fromisoformat)
    parser.add_argument("--created-to", type=date.fromisoformat)
    parser.add_argument("--keep-delivery-dates", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    _load_dotenv(Path(".env"))
    asyncio.run(_fix_order_dates(args))


if __name__ == "__main__":
    main()
