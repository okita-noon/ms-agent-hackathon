#!/usr/bin/env python3
"""Sync products from Azure SQL to Azure AI Search.

Reads all rows from the ``products`` table (joined with ``product_aliases`` for
the composite ``search_text`` field) and bulk-uploads them to the AI Search
``products`` index.

Prerequisites
-------------
- ``azure-search-documents>=11.5.0`` installed (included in requirements.txt)
- The ``products`` index must already exist in AI Search.
  Create it first::

      az rest --method PUT \
        --url "https://<service>.search.windows.net/indexes/products?api-version=2023-11-01" \
        --headers "Content-Type=application/json" "api-key=<key>" \
        --body @infra/search/products-index.json

Usage
-----
    python scripts/sync_products_to_search.py [--tenant-id T-001]

Environment variables required:
    SQL_CONNECTION_STRING   – pymssql-style or ODBC DSN
    AI_SEARCH_ENDPOINT      – e.g. https://search-orderai-dev.search.windows.net
    AI_SEARCH_KEY           – Admin key
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _build_odbc_dsn(connection: str) -> str:
    """Convert a pymssql-style connection string to ODBC if needed."""
    if connection.upper().startswith("DRIVER="):
        return connection  # already ODBC format
    # Heuristic: treat as "server;database;uid;pwd" semicolon-separated KV
    params = dict(p.split("=", 1) for p in connection.split(";") if "=" in p)
    server = params.get("Server") or params.get("server", "")
    database = params.get("Database") or params.get("database", "")
    uid = params.get("User ID") or params.get("uid", "")
    pwd = params.get("Password") or params.get("pwd", "")
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};DATABASE={database};"
        f"UID={uid};PWD={pwd};Encrypt=yes;TrustServerCertificate=no"
    )


def fetch_products(conn_str: str, tenant_id: str | None) -> list[dict]:
    """Return product rows (+ aliases) from Azure SQL as a list of dicts."""
    try:
        import pyodbc  # type: ignore
    except ImportError:
        # Fallback: try aioodbc's underlying driver via sync pyodbc
        try:
            import pyodbc  # type: ignore
        except ImportError:
            logger.error("pyodbc is not installed. Install it or use the Docker container.")
            sys.exit(1)

    dsn = _build_odbc_dsn(conn_str)
    conn = pyodbc.connect(dsn, timeout=30)
    cursor = conn.cursor()

    tenant_clause = "AND p.tenant_id = ?" if tenant_id else ""
    params: tuple = (tenant_id,) if tenant_id else ()

    sql = f"""
        SELECT
            p.product_id,
            p.tenant_id,
            p.name,
            p.display_name,
            p.category,
            p.default_unit,
            p.temperature_zone,
            p.unit_weight_kg,
            p.is_variable_weight,
            p.price_per_unit,
            p.active,
            STRING_AGG(pa.alias_name, ' ') AS alias_names
        FROM products p
        LEFT JOIN product_aliases pa
            ON p.product_id = pa.product_id AND p.tenant_id = pa.tenant_id
        WHERE 1=1 {tenant_clause}
        GROUP BY
            p.product_id, p.tenant_id, p.name, p.display_name, p.category,
            p.default_unit, p.temperature_zone, p.unit_weight_kg,
            p.is_variable_weight, p.price_per_unit, p.active
        ORDER BY p.tenant_id, p.name
    """
    cursor.execute(sql, params)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------

def build_document(row: dict) -> dict:
    """Convert a SQL row dict to an AI Search document dict."""
    name = row.get("name") or ""
    display_name = row.get("display_name") or ""
    alias_names = row.get("alias_names") or ""
    # Combine name + display_name + aliases into a single searchable field
    search_text = " ".join(filter(None, [name, display_name, alias_names]))

    return {
        "product_id": row["product_id"],
        "tenant_id": row["tenant_id"],
        "name": name,
        "display_name": display_name if display_name else None,
        "search_text": search_text,
        "category": row.get("category"),
        "default_unit": row.get("default_unit"),
        "temperature_zone": row.get("temperature_zone"),
        "unit_weight_kg": float(row["unit_weight_kg"]) if row.get("unit_weight_kg") is not None else None,
        "is_variable_weight": bool(row.get("is_variable_weight", False)),
        "price_per_unit": float(row["price_per_unit"]) if row.get("price_per_unit") is not None else None,
        "active": bool(row.get("active", True)),
    }


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_to_search(docs: list[dict], endpoint: str, api_key: str) -> None:
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    client = SearchClient(
        endpoint=endpoint,
        index_name="products",
        credential=AzureKeyCredential(api_key),
    )

    batch_size = 100
    total_uploaded = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        result = client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        failed = len(batch) - succeeded
        total_uploaded += succeeded
        if failed:
            logger.warning("Batch %d: %d failed", i // batch_size + 1, failed)
        logger.info("Batch %d: %d/%d uploaded", i // batch_size + 1, succeeded, len(batch))

    logger.info("Done. Total uploaded: %d / %d", total_uploaded, len(docs))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync products from SQL to AI Search")
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Sync only this tenant (default: all tenants)",
    )
    args = parser.parse_args()

    sql_conn = os.environ.get("SQL_CONNECTION_STRING")
    search_endpoint = os.environ.get("AI_SEARCH_ENDPOINT")
    search_key = os.environ.get("AI_SEARCH_KEY")

    if not sql_conn:
        logger.error("SQL_CONNECTION_STRING environment variable is not set.")
        sys.exit(1)
    if not search_endpoint:
        logger.error("AI_SEARCH_ENDPOINT environment variable is not set.")
        sys.exit(1)
    if not search_key:
        logger.error("AI_SEARCH_KEY environment variable is not set.")
        sys.exit(1)

    logger.info("Fetching products from SQL (tenant_id=%s) ...", args.tenant_id or "all")
    rows = fetch_products(sql_conn, args.tenant_id)
    logger.info("Fetched %d products.", len(rows))

    if not rows:
        logger.warning("No products found – nothing to upload.")
        return

    docs = [build_document(r) for r in rows]

    logger.info("Uploading %d documents to AI Search index 'products' ...", len(docs))
    upload_to_search(docs, search_endpoint, search_key)


if __name__ == "__main__":
    main()
