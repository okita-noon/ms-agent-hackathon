"""Regression tests for frontend deploy config consistency."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
VITE_CONFIG = ROOT / "frontend" / "vite.config.ts"
DEPLOY_YML = ROOT / ".github" / "workflows" / "deploy-frontend.yml"
MSAL_CONFIG = ROOT / "frontend" / "src" / "auth" / "msalConfig.ts"
MAIN_TSX = ROOT / "frontend" / "src" / "main.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_vite_base_is_root() -> None:
    """Vite base must be '/' so assets resolve from root."""
    text = _read(VITE_CONFIG)
    assert 'base: "/"' in text, "vite.config.ts base should be '/'"


def test_deploy_yml_no_dashboard_destination_path() -> None:
    """deploy-frontend.yml must not use a --destination-path prefix."""
    text = _read(DEPLOY_YML)
    assert "--destination-path" not in text, (
        "deploy-frontend.yml should not use --destination-path (files deploy to root)"
    )


def test_deploy_yml_404_document_is_root_index() -> None:
    """The 404 document must be root-level index.html for SPA routing."""
    text = _read(DEPLOY_YML)
    assert '--404-document "index.html"' in text, "404 document must be 'index.html' (not 'dashboard/index.html')"


def test_msal_redirect_uri_is_origin() -> None:
    """MSAL redirectUri must be window.location.origin (no path suffix)."""
    text = _read(MSAL_CONFIG)
    assert "window.location.origin," in text or "window.location.origin\n" in text, (
        "msalConfig.ts redirectUri should be window.location.origin with no path"
    )
    assert "/dashboard" not in text.split("redirectUri")[1].split("\n")[0], "redirectUri must not contain /dashboard"


def test_browser_router_has_empty_basename() -> None:
    """BrowserRouter basename must be empty string for root-based routing."""
    text = _read(MAIN_TSX)
    assert 'basename=""' in text, "BrowserRouter basename should be empty string"
    assert 'basename="/dashboard"' not in text


def test_main_tsx_has_popup_guard() -> None:
    """main.tsx must include the popup guard to prevent React rendering in MSAL popups."""
    text = _read(MAIN_TSX)
    assert "window.opener" in text, "main.tsx must have popup guard (window.opener check)"
    assert "msalReady" in text, "main.tsx must import and call msalReady in popup context"


def test_no_duplicate_page_size_in_orders() -> None:
    """PAGE_SIZE must not be declared twice in Orders.tsx (regression for merge artifact)."""
    orders_tsx = ROOT / "frontend" / "src" / "pages" / "Orders.tsx"
    if not orders_tsx.exists():
        return
    text = _read(orders_tsx)
    matches = re.findall(r"const\s+PAGE_SIZE\s*=", text)
    assert len(matches) <= 1, f"Duplicate PAGE_SIZE declaration ({len(matches)} occurrences)"


def test_deploy_yml_no_frontend_path_env() -> None:
    """FRONTEND_PATH env var should be removed from deploy workflow."""
    text = _read(DEPLOY_YML)
    assert "FRONTEND_PATH" not in text, "FRONTEND_PATH env var should be removed; files now deploy to root"
