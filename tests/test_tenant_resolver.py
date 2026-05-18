from __future__ import annotations

from unittest.mock import patch

from src.services.tenant_resolver import (
    _TENANT_CACHE,
    get_demo_tenant_config,
    resolve_tenant_by_id,
    resolve_tenant_for_line,
)


class TestGetDemoTenantConfig:
    @patch.dict(
        "os.environ",
        {
            "COSMOS_CONNECTION_STRING": "cosmos-conn",
            "SQL_CONNECTION_STRING": "sql-conn",
            "LINE_CHANNEL_ID": "ch-id",
            "LINE_CHANNEL_SECRET": "ch-secret",
            "LINE_CHANNEL_ACCESS_TOKEN": "ch-token",
        },
    )
    def test_loads_from_env(self):
        cfg = get_demo_tenant_config()
        assert cfg.tenant_id == "T-001"
        assert cfg.line_channel_id == "ch-id"
        assert cfg.line_channel_secret == "ch-secret"
        assert cfg.connectors["IOrderRepository"].connection == "cosmos-conn"
        assert cfg.connectors["IProductMaster"].connection == "sql-conn"

    @patch.dict("os.environ", {}, clear=True)
    def test_defaults_to_empty(self):
        _TENANT_CACHE.clear()
        cfg = get_demo_tenant_config()
        assert cfg.connectors["IOrderRepository"].connection == ""


class TestResolveTenant:
    @patch.dict(
        "os.environ", {"COSMOS_CONNECTION_STRING": "c", "SQL_CONNECTION_STRING": "s"}
    )
    def test_resolve_for_line(self):
        _TENANT_CACHE.clear()
        ctx = resolve_tenant_for_line("some-destination")
        assert ctx.tenant_id == "T-001"

    @patch.dict(
        "os.environ", {"COSMOS_CONNECTION_STRING": "c", "SQL_CONNECTION_STRING": "s"}
    )
    def test_resolve_by_id(self):
        _TENANT_CACHE.clear()
        ctx = resolve_tenant_by_id("T-002")
        assert ctx.tenant_id == "T-002"
