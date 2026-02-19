"""E2E tests for multi-connection dispatch.

These tests use real sqlite databases and on-disk connection directories to
exercise connection discovery + dispatch logic end-to-end.
"""

from __future__ import annotations

import sqlite3

import pytest

from db_mcp.config import Settings
from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.generation import _execute_query


def _init_sqlite(db_path, value: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE t(v TEXT)")
        conn.execute("INSERT INTO t(v) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_run_sql_dispatches_by_connection_name(tmp_path):
    connections_dir = tmp_path / "connections"

    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _init_sqlite(db_a, "A")
    _init_sqlite(db_b, "B")

    # Connection A
    (connections_dir / "a").mkdir(parents=True)
    (connections_dir / "a" / "connector.yaml").write_text(
        "\n".join(
            [
                "type: sql",
                "dialect: sqlite",
                f"database_url: sqlite:///{db_a}",
                "capabilities:",
                "  supports_validate_sql: false",
            ]
        )
        + "\n"
    )

    # Connection B
    (connections_dir / "b").mkdir(parents=True)
    (connections_dir / "b" / "connector.yaml").write_text(
        "\n".join(
            [
                "type: sql",
                "dialect: sqlite",
                f"database_url: sqlite:///{db_b}",
                "capabilities:",
                "  supports_validate_sql: false",
            ]
        )
        + "\n"
    )

    settings = Settings(connections_dir=str(connections_dir), connection_name="a")
    ConnectionRegistry.reset()
    ConnectionRegistry.get_instance(settings)

    res_a = _execute_query("SELECT v FROM t", connection="a")
    assert res_a["status"] == "success"
    assert res_a["data"][0]["v"] == "A"
    assert res_a["provider_id"] == "a"

    res_b = _execute_query("SELECT v FROM t", connection="b")
    assert res_b["status"] == "success"
    assert res_b["data"][0]["v"] == "B"
    assert res_b["provider_id"] == "b"


@pytest.mark.asyncio
async def test_run_sql_ambiguous_without_connection_lists_available(tmp_path):
    connections_dir = tmp_path / "connections"

    db_a = tmp_path / "a.sqlite"
    db_b = tmp_path / "b.sqlite"
    _init_sqlite(db_a, "A")
    _init_sqlite(db_b, "B")

    for name, db in [("a", db_a), ("b", db_b)]:
        (connections_dir / name).mkdir(parents=True)
        (connections_dir / name / "connector.yaml").write_text(
            "\n".join(
                [
                    "type: sql",
                    "dialect: sqlite",
                    f"database_url: sqlite:///{db}",
                    "capabilities:",
                    "  supports_validate_sql: false",
                ]
            )
            + "\n"
        )

    settings = Settings(connections_dir=str(connections_dir), connection_name="a")
    ConnectionRegistry.reset()
    ConnectionRegistry.get_instance(settings)

    with pytest.raises(ValueError) as e:
        _execute_query("SELECT v FROM t")

    msg = str(e.value)
    assert "Multiple sql connections available" in msg
    assert "a" in msg
    assert "b" in msg
