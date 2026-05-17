#!/usr/bin/env python3
"""Seed demo users into Azure SQL.

Usage:
    DEMO_PASSWORD=yourpassword SQL_CONNECTION_STRING=... python scripts/seed_users.py

Requires:
  - SQL_CONNECTION_STRING: Azure SQL connection string (env or .env)
  - DEMO_PASSWORD: Password for demo users (env, required)
"""
from __future__ import annotations

import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


DEMO_USERS = [
    ("U-001", "T-001", "admin@maruyama.example.com", "丸山 太郎", "local"),
    ("U-002", "T-001", "staff@maruyama.example.com", "丸山 花子", "local"),
    ("U-003", "T-002", "admin@suzuki.example.com", "鈴木 一郎", "local"),
    ("U-004", "T-002", "staff@suzuki.example.com", "鈴木 次郎", "local"),
]

SQL = """
IF NOT EXISTS (SELECT 1 FROM users WHERE user_id = ?)
    INSERT INTO users (user_id, tenant_id, email, password_hash, display_name, auth_provider)
    VALUES (?, ?, ?, ?, ?, ?);
"""


def main() -> None:
    demo_password = os.environ.get("DEMO_PASSWORD")
    if not demo_password:
        print("ERROR: DEMO_PASSWORD environment variable is required")
        sys.exit(1)

    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        # Try loading from .env
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SQL_CONNECTION_STRING="):
                        conn_str = line.split("=", 1)[1].strip('"').strip("'")
                        break

    if not conn_str:
        print("ERROR: SQL_CONNECTION_STRING not set")
        sys.exit(1)

    hashed = pwd_context.hash(demo_password)

    try:
        import pyodbc

        conn = pyodbc.connect(conn_str)
    except ImportError:
        print("ERROR: pyodbc not installed. Run: pip install pyodbc")
        sys.exit(1)

    cursor = conn.cursor()
    for user_id, tenant_id, email, name, provider in DEMO_USERS:
        cursor.execute(SQL, (user_id, user_id, tenant_id, email, hashed, name, provider))
        print(f"  {'inserted' if cursor.rowcount else 'skipped'}: {email} ({user_id})")

    conn.commit()
    conn.close()
    print("\nDone. Users seeded successfully.")


if __name__ == "__main__":
    main()
