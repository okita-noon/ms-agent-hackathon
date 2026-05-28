"""
在庫補充スクリプト
Created: 2026-05-28

使い方:
    # デフォルト設定でリセット（007-reset-inventory.sql の内容と同じ）
    python scripts/add_stock/run.py

    # 全商品を指定数量に設定
    python scripts/add_stock/run.py --qty 500

    # 特定商品だけ指定
    python scripts/add_stock/run.py --product P-008 --qty 50

    # dry-run（SQL確認のみ、実行しない）
    python scripts/add_stock/run.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Windows でのUTF-8出力を強制
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]

# デフォルト在庫設定
DEFAULT_STOCK: dict[str, int] = {
    "P-001": 0,     # りんご: 欠品のまま
    "P-002": 1000,  # バナナ
    "P-003": 1000,  # みかん
    "P-004": 1000,  # ぶどう
    "P-005": 1000,  # もも
    "P-006": 1000,  # いちご
    "P-007": 30,    # メロン: 在庫不足テスト用
    "P-008": 30,    # スイカ: 在庫不足テスト用
    "P-009": 1000,  # 梨
    "P-010": 1000,  # マンゴー
    "P-011": 1000,  # キウイ
    "P-012": 30,    # さくらんぼ: 在庫不足テスト用
    "P-013": 1000,  # いちじく
    "P-014": 1000,  # レモン
    "P-015": 1000,  # アボカド
    "P-016": 1000,  # にんにく
    "P-017": 1000,  # ブルーベリー
}

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
    # Key Vault から取得を試みる
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


def _run(conn_str: str, stock: dict[str, int], dry_run: bool) -> None:
    statements = []
    for product_id, qty in sorted(stock.items()):
        statements.append(
            f"UPDATE inventory SET quantity = {qty}, reserved_qty = 0 "
            f"WHERE tenant_id = '{TENANT_ID}' AND product_id = '{product_id}';"
        )

    if dry_run:
        print("【dry-run】以下のSQLを実行します：")
        for s in statements:
            print(f"  {s}")
        return

    try:
        import pyodbc
        conn = pyodbc.connect(conn_str)
    except ImportError:
        # pyodbc がなければ pymssql を試みる
        import pymssql  # type: ignore
        # pymssql 用に接続文字列をパース
        parts = {k.strip(): v.strip() for k, v in
                 (item.split("=", 1) for item in conn_str.split(";") if "=" in item)}
        server = parts.get("Server", "").replace("tcp:", "").split(",")[0]
        db = parts.get("Database", parts.get("Initial Catalog", ""))
        user = parts.get("User ID", parts.get("UID", ""))
        password = parts.get("Password", parts.get("PWD", ""))
        conn = pymssql.connect(server=server, database=db, user=user, password=password)

    cursor = conn.cursor()
    ok = 0
    for stmt in statements:
        try:
            cursor.execute(stmt)
            print(f"OK: {stmt[:70]}")
            ok += 1
        except Exception as e:
            print(f"ERR: {e} | {stmt[:70]}")
    conn.commit()
    conn.close()
    print(f"\n完了: {ok}/{len(statements)} 件更新しました。")


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="在庫補充スクリプト")
    parser.add_argument("--product", default=None, help="特定商品IDのみ更新（例: P-008）")
    parser.add_argument("--qty", type=int, default=None, help="設定する数量（デフォルト設定を上書き）")
    parser.add_argument("--dry-run", action="store_true", help="SQLを表示するだけで実行しない")
    args = parser.parse_args()

    stock = dict(DEFAULT_STOCK)

    if args.product:
        if args.product not in stock:
            print(f"エラー: 商品ID '{args.product}' が見つかりません。")
            sys.exit(1)
        qty = args.qty if args.qty is not None else stock[args.product]
        stock = {args.product: qty}
    elif args.qty is not None:
        stock = {pid: args.qty for pid in stock}

    conn_str = "" if args.dry_run else _get_conn_str()
    _run(conn_str, stock, args.dry_run)


if __name__ == "__main__":
    main()
