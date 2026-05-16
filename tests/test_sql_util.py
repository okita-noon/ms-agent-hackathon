from __future__ import annotations

from src.connectors.adapters._sql_util import to_odbc_dsn


class TestToOdbcDsn:
    def test_converts_adonet_to_odbc(self):
        adonet = (
            "Server=tcp:sql-orderai-dev.database.windows.net,1433;"
            "Database=db-orderai-dev;"
            "User ID=sqladmin;"
            "Password=secret123;"
            "Encrypt=true;"
            "TrustServerCertificate=false;"
            "Connection Timeout=30;"
        )
        dsn = to_odbc_dsn(adonet)
        assert "Driver={ODBC Driver 18 for SQL Server}" in dsn
        assert "Server=sql-orderai-dev.database.windows.net,1433" in dsn
        assert "Database=db-orderai-dev" in dsn
        assert "UID=sqladmin" in dsn
        assert "PWD=secret123" in dsn

    def test_passthrough_if_driver_present(self):
        odbc = "Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=test;"
        assert to_odbc_dsn(odbc) == odbc

    def test_passthrough_if_dsn_present(self):
        dsn = "DSN=mydsn;UID=user;PWD=pass;"
        assert to_odbc_dsn(dsn) == dsn

    def test_empty_string(self):
        assert to_odbc_dsn("") == ""

    def test_server_without_tcp_prefix(self):
        conn = "Server=myserver.database.windows.net,1433;Database=mydb;User ID=user;Password=pass;"
        dsn = to_odbc_dsn(conn)
        assert "Server=myserver.database.windows.net,1433" in dsn

    def test_server_without_port(self):
        conn = "Server=tcp:myserver.database.windows.net;Database=mydb;User ID=user;Password=pass;"
        dsn = to_odbc_dsn(conn)
        assert "Server=myserver.database.windows.net,1433" in dsn
