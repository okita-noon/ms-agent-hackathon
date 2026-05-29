"""
在庫チェック・補正スクリプト
Created: 2026-05-29

expected_stock.json の min/max と現在の在庫を比較し、
範囲外の商品を自動補正する。

使い方:
    # チェックのみ（補正しない）
    python scripts/check_stock/run.py --dry-run

    # チェック＋自動補正
    python scripts/check_stock/run.py

    # ローカル .env を使う場合
    python scripts/check_stock/run.py --env .env
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_STOCK_FILE = Path(__file__).resolve().parent / "expected_stock.json"
TENANT_ID = "T-001"


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


def _get_conn_str() -> str:
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
    if conn_str:
        return conn_str
    try:
        import subprocess
        result = subprocess.run(
            ["az", "keyvault", "secret", "show",
             "--vault-name", "kv-orderai-dev2",
             "--name", "sql-connection-string",
             "--query", "value", "-o", "tsv"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    raise RuntimeError("SQL_CONNECTION_STRING が取得できませんでした。.env に設定するか az login してください。")


def _get_connection(conn_str: str):
    try:
        import pymssql  # type: ignore
        parts = {k.strip(): v.strip() for k, v in
                 (item.split("=", 1) for item in conn_str.split(";") if "=" in item)}
        server = parts.get("Server", "").replace("tcp:", "").split(",")[0]
        db = parts.get("Database", parts.get("Initial Catalog", ""))
        user = parts.get("User ID", parts.get("UID", ""))
        password = parts.get("Password", parts.get("PWD", ""))
        return pymssql.connect(server=server, database=db, user=user, password=password)
    except ImportError:
        import pyodbc
        return pyodbc.connect(conn_str)


def main() -> None:
    parser = argparse.ArgumentParser(description="在庫チェック・補正スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="チェックのみ。補正しない")
    parser.add_argument("--env", default=None, help=".envファイルのパス")
    args = parser.parse_args()

    _load_dotenv(Path(args.env) if args.env else REPO_ROOT / ".env")

    # 期待在庫を読み込む
    expected = json.loads(EXPECTED_STOCK_FILE.read_text(encoding="utf-8"))
    products = {p["product_id"]: p for p in expected["products"]}

    conn_str = _get_conn_str()
    conn = _get_connection(conn_str)
    cursor = conn.cursor()

    # 現在の在庫を取得
    cursor.execute(
        f"SELECT product_id, quantity FROM inventory WHERE tenant_id = '{TENANT_ID}' ORDER BY product_id"
    )
    current = {row[0]: float(row[1]) for row in cursor.fetchall()}

    # チェック
    issues: list[tuple[str, float, int]] = []  # (product_id, current_qty, target_qty)
    ok_count = 0

    print("── 在庫チェック ──────────────────────────")
    for pid, spec in products.items():
        qty = current.get(pid, 0)
        min_qty = spec["min"]
        max_qty = spec["max"]
        name = spec["name"]

        if qty < min_qty:
            target = min_qty
            print(f"  NG {pid} {name}: {int(qty)} < min={min_qty} → {target} に補充")
            issues.append((pid, qty, target))
        elif qty > max_qty:
            target = max_qty
            print(f"  NG {pid} {name}: {int(qty)} > max={max_qty} → {target} に削減")
            issues.append((pid, qty, target))
        else:
            print(f"  OK {pid} {name}: {int(qty)} (min={min_qty}, max={max_qty})")
            ok_count += 1

    print(f"\n結果: {ok_count}OK / {len(issues)}NG")

    if not issues:
        print("在庫は全て正常範囲内ですわ。")
        conn.close()
        return

    if args.dry_run:
        print("\n[dry-run] 補正はスキップしました。")
        conn.close()
        return

    # 補正実行
    print("\n── 在庫補正 ──────────────────────────")
    fixed = 0
    for pid, current_qty, target_qty in issues:
        name = products[pid]["name"]
        try:
            cursor.execute(
                f"UPDATE inventory SET quantity = {target_qty}, reserved_qty = 0 "
                f"WHERE tenant_id = '{TENANT_ID}' AND product_id = '{pid}'"
            )
            print(f"  補正 {pid} {name}: {int(current_qty)} → {target_qty}")
            fixed += 1
        except Exception as e:
            print(f"  ERR {pid} {name}: {e}")

    conn.commit()
    conn.close()
    print(f"\n補正完了: {fixed}/{len(issues)} 件")


if __name__ == "__main__":
    main()
