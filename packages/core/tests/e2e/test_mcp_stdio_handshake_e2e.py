from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport


def _init_sqlite(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t(v) VALUES ('a'), ('b')")
        conn.commit()
    finally:
        conn.close()


def _write_connection(connections_dir: Path, name: str, db_path: Path) -> Path:
    conn_path = connections_dir / name
    conn_path.mkdir(parents=True)
    (conn_path / "connector.yaml").write_text(
        "\n".join(
            [
                "type: sql",
                f"database_url: sqlite:///{db_path}",
                "capabilities:",
                "  supports_validate_sql: true",
                "  supports_async_jobs: true",
            ]
        )
        + "\n"
    )
    return conn_path


@pytest.mark.asyncio
async def test_stdio_initialize_list_tools_and_call_ping(tmp_path):
    connections_dir = tmp_path / "connections"
    db_path = tmp_path / "playground.sqlite"
    _init_sqlite(db_path)
    conn_path = _write_connection(connections_dir, "playground", db_path)

    env = os.environ.copy()
    env.update(
        {
            "CONNECTIONS_DIR": str(connections_dir),
            "CONNECTION_PATH": str(conn_path),
            "DB_MCP_CONNECTION_PATH": str(conn_path),
            "CONNECTION_NAME": "playground",
            "TOOL_MODE": "detailed",
            "MCP_TRANSPORT": "stdio",
            "LOG_LEVEL": "ERROR",
        }
    )

    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "db_mcp.server"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
    )

    async with Client(transport, auto_initialize=False, init_timeout=20, timeout=20) as client:
        init_result = await client.initialize()
        assert init_result.serverInfo.name == "db-mcp"

        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        assert "ping" in tool_names
        assert "list_connections" in tool_names

        ping = await client.call_tool("ping", {})
        assert isinstance(ping.data, dict)
        assert ping.data["status"] == "ok"
        assert ping.data["connection"] == "playground"
