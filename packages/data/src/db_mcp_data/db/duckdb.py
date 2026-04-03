"""In-memory DuckDB execution engine for file-based queries."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

import duckdb

from db_mcp_data.db.connection import DatabaseError

if TYPE_CHECKING:
    from db_mcp_data.connectors.file import FileSourceConfig

_EXT_RE = re.compile(r"\.(\w+)$")

_FORMAT_MAP: dict[str, str] = {
    "csv": "read_csv_auto",
    "tsv": "read_csv_auto",
    "parquet": "read_parquet",
    "json": "read_json_auto",
    "jsonl": "read_json_auto",
    "ndjson": "read_json_auto",
}


def _read_function_for_path(path: str) -> str:
    clean = path.rstrip("*").rstrip("/")
    m = _EXT_RE.search(clean)
    if not m:
        raise ValueError(f"Cannot determine file format from path: {path}")
    ext = m.group(1).lower()
    if ext not in _FORMAT_MAP:
        raise ValueError(f"Unsupported file extension: .{ext}")
    return _FORMAT_MAP[ext]


class DuckDBExecutor:
    """In-memory DuckDB engine that creates views from file sources and executes SQL.

    The caller provides a ``get_sources`` callable that returns the current list of
    ``FileSourceConfig`` objects. DuckDBExecutor calls it lazily when it needs to
    build (or rebuild) its in-memory views.
    """

    def __init__(self, get_sources: Callable[[], list[FileSourceConfig]]) -> None:
        self._get_sources = get_sources
        self._conn: duckdb.DuckDBPyConnection | None = None

    def invalidate(self) -> None:
        """Drop the in-memory connection so views are rebuilt on the next query."""
        self._conn = None

    def _ensure_connection(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(":memory:")
            self._create_views(self._conn)
        return self._conn

    def _create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        for source in self._get_sources():
            func = _read_function_for_path(source.path)
            if func == "read_parquet":
                expr = f"read_parquet('{source.path}', hive_partitioning=true)"
            else:
                expr = f"{func}('{source.path}')"
            conn.execute(f'CREATE OR REPLACE VIEW "{source.name}" AS SELECT * FROM {expr}')

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        conn = self._ensure_connection()
        try:
            result = conn.execute(sql)
        except (duckdb.CatalogException, duckdb.BinderException, duckdb.ParserException) as exc:
            raise DatabaseError(str(exc)) from exc
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def get_columns(self, table_name: str) -> list[dict[str, Any]]:
        conn = self._ensure_connection()
        try:
            rows = conn.execute(f'DESCRIBE "{table_name}"').fetchall()
        except duckdb.CatalogException as exc:
            raise DatabaseError(str(exc)) from exc
        return [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
                "primary_key": False,
                "comment": None,
            }
            for row in rows
        ]

    def get_table_sample(self, table_name: str, limit: int = 5) -> list[dict[str, Any]]:
        conn = self._ensure_connection()
        result = conn.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}')
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]
