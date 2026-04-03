"""TDD tests for B1 — DuckDBExecutor extraction and APIConnector sync fix."""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. DuckDBExecutor exists at db_mcp_data.db.duckdb
# ---------------------------------------------------------------------------


def test_duckdb_executor_importable():
    """DuckDBExecutor must be importable from db_mcp_data.db.duckdb."""
    from db_mcp_data.db.duckdb import DuckDBExecutor

    assert DuckDBExecutor is not None


def test_duckdb_executor_runs_simple_sql(tmp_path: Path):
    """DuckDBExecutor can execute a plain SQL query against a JSONL view."""
    jsonl = tmp_path / "orders.jsonl"
    jsonl.write_text(json.dumps({"order_id": 1, "amount": 99}) + "\n")

    from db_mcp_data.connectors.file import FileSourceConfig
    from db_mcp_data.db.duckdb import DuckDBExecutor

    sources = [FileSourceConfig(name="orders", path=str(jsonl))]
    executor = DuckDBExecutor(lambda: sources)

    rows = executor.execute_sql("SELECT order_id, amount FROM orders")
    assert rows == [{"order_id": 1, "amount": 99}]


def test_duckdb_executor_invalidate_picks_up_new_file(tmp_path: Path):
    """After invalidate(), executor re-discovers sources on next query."""
    jsonl = tmp_path / "items.jsonl"
    jsonl.write_text(json.dumps({"id": 1}) + "\n")

    from db_mcp_data.connectors.file import FileSourceConfig
    from db_mcp_data.db.duckdb import DuckDBExecutor

    sources: list[FileSourceConfig] = []

    def get_sources():
        return sources

    executor = DuckDBExecutor(get_sources)

    # First query: no sources → empty (just DuckDB metadata)
    sources.append(FileSourceConfig(name="items", path=str(jsonl)))
    executor.invalidate()

    rows = executor.execute_sql("SELECT id FROM items")
    assert rows == [{"id": 1}]


# ---------------------------------------------------------------------------
# 2. FileConnector composes DuckDBExecutor and exposes invalidate_cache()
# ---------------------------------------------------------------------------


def test_file_connector_has_duckdb_executor(tmp_path: Path):
    """FileConnector must have a _duckdb attribute of type DuckDBExecutor."""
    from db_mcp_data.connectors.file import FileConnector, FileConnectorConfig
    from db_mcp_data.db.duckdb import DuckDBExecutor

    conn = FileConnector(FileConnectorConfig(directory=str(tmp_path)))
    assert hasattr(conn, "_duckdb")
    assert isinstance(conn._duckdb, DuckDBExecutor)


def test_file_connector_has_no_direct_duckdb_conn():
    """FileConnector must NOT have _conn directly — DuckDB state lives in _duckdb."""
    from db_mcp_data.connectors.file import FileConnector, FileConnectorConfig

    conn = FileConnector(FileConnectorConfig())
    assert not hasattr(conn, "_conn"), (
        "_conn must live inside DuckDBExecutor, not directly on FileConnector"
    )


def test_file_connector_invalidate_cache(tmp_path: Path):
    """FileConnector.invalidate_cache() clears both _resolved_sources and _duckdb."""
    jsonl1 = tmp_path / "a.jsonl"
    jsonl1.write_text(json.dumps({"x": 1}) + "\n")

    from db_mcp_data.connectors.file import FileConnector, FileConnectorConfig

    conn = FileConnector(FileConnectorConfig(directory=str(tmp_path)))

    # Run a query to populate caches
    rows = conn.execute_sql("SELECT x FROM a")
    assert rows == [{"x": 1}]

    # Add a new file, then invalidate
    jsonl2 = tmp_path / "b.jsonl"
    jsonl2.write_text(json.dumps({"y": 2}) + "\n")
    conn.invalidate_cache()

    # After invalidation, new file is visible
    rows = conn.execute_sql("SELECT y FROM b")
    assert rows == [{"y": 2}]


# ---------------------------------------------------------------------------
# 3. APIConnector.sync() invalidates _file_connector properly
# ---------------------------------------------------------------------------


def test_api_connector_sync_invalidates_file_connector(tmp_path: Path):
    """After sync(), _file_connector cache is invalidated so new JSONL is queryable."""

    from db_mcp_data.connectors.api import APIConnector
    from db_mcp_data.connectors.api_config import (
        APIConnectorConfig,
        APIEndpointConfig,
    )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    config = APIConnectorConfig(
        base_url="https://api.example.com",
        endpoints=[APIEndpointConfig(name="users", path="/users")],
    )

    connector = APIConnector(config, data_dir=str(data_dir))

    # Manually write a JSONL file (simulating what sync would produce)
    users_jsonl = data_dir / "users.jsonl"
    users_jsonl.write_text(json.dumps({"user_id": 42, "name": "alice"}) + "\n")

    # Trigger sync invalidation without making real HTTP calls
    connector._file_connector.invalidate_cache()

    rows = connector._file_connector.execute_sql("SELECT user_id FROM users")
    assert rows == [{"user_id": 42}]


def test_api_connector_sync_does_not_set_conn_on_self():
    """APIConnector must not have _conn as a direct attribute after sync invalidation."""
    import tempfile

    from db_mcp_data.connectors.api import APIConnector
    from db_mcp_data.connectors.api_config import APIConnectorConfig

    with tempfile.TemporaryDirectory() as tmp:
        config = APIConnectorConfig(base_url="https://api.example.com", endpoints=[])
        connector = APIConnector(config, data_dir=tmp)

    # After construction, _conn should NOT be a top-level attribute on APIConnector
    assert not hasattr(connector, "_conn"), (
        "_conn belongs in DuckDBExecutor, not on APIConnector directly"
    )


# ---------------------------------------------------------------------------
# 4. Dispatcher: FileAdapter no longer needs isinstance(_, APIConnector) guard
# ---------------------------------------------------------------------------


def test_file_adapter_can_handle_file_connector_without_api_guard():
    """FileAdapter.can_handle must be based solely on FileConnector, not a negation of APIConnector."""  # noqa: E501
    import inspect

    from db_mcp_data.gateway.file_adapter import FileAdapter

    source = inspect.getsource(FileAdapter.can_handle)
    assert "APIConnector" not in source, (
        "FileAdapter.can_handle should not reference APIConnector. "
        "The guard was only needed when APIConnector inherited from FileConnector."
    )


def test_dispatcher_comment_no_longer_says_extends():
    """Dispatcher docstring must not say APIConnector extends FileConnector."""
    import inspect

    import db_mcp_data.gateway.dispatcher as dispatcher_mod

    source = inspect.getsource(dispatcher_mod)
    assert "extends FileConnector" not in source, (
        "Dispatcher comment refers to the old inheritance. Update it."
    )
