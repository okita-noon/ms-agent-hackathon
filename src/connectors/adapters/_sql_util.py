from __future__ import annotations

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


def to_odbc_dsn(conn_str: str) -> str:
    """Ensure an ADO.NET-style connection string has an ODBC Driver clause."""
    if not conn_str:
        return conn_str
    upper = conn_str.upper()
    if "DRIVER=" in upper or "DSN=" in upper:
        return conn_str

    parts: dict[str, str] = {}
    for segment in conn_str.split(";"):
        segment = segment.strip()
        if "=" not in segment:
            continue
        key, _, val = segment.partition("=")
        parts[key.strip()] = val.strip()

    server = parts.get("Server", parts.get("server", ""))
    if server.startswith("tcp:"):
        host_port = server[4:]
    else:
        host_port = server

    if "," in host_port:
        host, port = host_port.rsplit(",", 1)
    else:
        host, port = host_port, "1433"

    database = parts.get("Database", parts.get("Initial Catalog", ""))
    uid = parts.get("User ID", parts.get("UID", ""))
    pwd = parts.get("Password", parts.get("Pwd", ""))

    dsn = (
        f"Driver={{{ODBC_DRIVER}}};"
        f"Server={host},{port};"
        f"Database={database};"
        f"UID={uid};"
        f"PWD={pwd};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    return dsn
