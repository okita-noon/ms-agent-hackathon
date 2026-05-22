"""ローカル開発用サーバー（SSO認証フロー検証専用）。

本番の main.py は azure-cosmos / aioodbc 等が必要なため、
認証フローのみを検証するための最小構成サーバー。
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.auth.endpoints import auth_router

app = FastAPI(title="OrderAI Auth Dev Server")

app.include_router(auth_router, prefix="/api/auth")

dashboard_dir = Path(__file__).parent / "src" / "dashboard"
app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard/")


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "local-dev"}
