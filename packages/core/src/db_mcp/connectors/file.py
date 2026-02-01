"""File connector — queries local CSV, Parquet, and JSON files via DuckDB."""

from __future__ import annotations

import glob as globmod
import re
from dataclasses import dataclass, field
from typing import Any

import duckdb

from db_mcp.db.connection import DatabaseError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class FileSourceConfig:
    """A single file source (one logical table)."""

    name: str
    path: str


@dataclass
class FileConnectorConfig:
    """Configuration for the file connector."""

    type: str = field(default="file", init=False)
    sources: list[FileSourceConfig] = field(default_factory=list)
    directory: str = ""


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_EXT_RE = re.compile(r"\.(\w+)$")

_FORMAT_MAP: dict[str, str] = {
    "csv": "read_csv_auto",
    "tsv": "read_csv_auto",
    "parquet": "read_parquet",
    "json": "read_json_auto",
    "jsonl": "read_json_auto",
    "ndjson": "read_json_auto",
}

_SUPPORTED_EXTENSIONS = set(_FORMAT_MAP.keys())


def _read_function_for_path(path: str) -> str:
    """Return the DuckDB read function name for a file path or glob pattern."""
    # Strip glob metacharacters to isolate the extension
    clean = path.rstrip("*").rstrip("/")
    m = _EXT_RE.search(clean)
    if not m:
        raise ValueError(f"Cannot determine file format from path: {path}")
    ext = m.group(1).lower()
    if ext not in _FORMAT_MAP:
        raise ValueError(f"Unsupported file extension: .{ext}")
    return _FORMAT_MAP[ext]


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


def _discover_directory(directory: str) -> list[FileSourceConfig]:
    """Scan a directory for supported files and return them as sources.

    Each file's stem (filename without extension) becomes the table name.
    Hidden files (starting with '.') are ignored.
    """
    from pathlib import Path

    dir_path = Path(directory).expanduser()
    if not dir_path.is_dir():
        return []

    sources: list[FileSourceConfig] = []
    for f in sorted(dir_path.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lstrip(".").lower()
        if ext in _SUPPORTED_EXTENSIONS:
            sources.append(FileSourceConfig(name=f.stem, path=str(f)))
    return sources


class FileConnector:
    """Connector that queries local files via an in-memory DuckDB instance."""

    def __init__(self, config: FileConnectorConfig) -> None:
        self.config = config
        self._resolved_sources: list[FileSourceConfig] | None = None
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_sources(self) -> list[FileSourceConfig]:
        """Return all sources: explicit + discovered from directory."""
        if self._resolved_sources is None:
            sources = list(self.config.sources)
            if self.config.directory:
                sources.extend(_discover_directory(self.config.directory))
            self._resolved_sources = sources
        return self._resolved_sources

    # -- lazy DuckDB setup --------------------------------------------------

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
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

    # -- Protocol methods ---------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        sources: dict[str, int] = {}
        errors: list[str] = []
        if self.config.directory:
            from pathlib import Path

            if not Path(self.config.directory).expanduser().is_dir():
                return {
                    "connected": False,
                    "dialect": "duckdb",
                    "sources": {},
                    "error": f"Directory does not exist: {self.config.directory}",
                }
        for source in self._get_sources():
            matches = globmod.glob(source.path)
            sources[source.name] = len(matches)
            if not matches:
                errors.append(f"{source.name}: no files match '{source.path}'")
        connected = len(errors) == 0
        return {
            "connected": connected,
            "dialect": "duckdb",
            "sources": sources,
            "error": "; ".join(errors) if errors else None,
        }

    def get_dialect(self) -> str:
        return "duckdb"

    def get_catalogs(self) -> list[str | None]:
        return [None]

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        return [None]

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "schema": None,
                "catalog": None,
                "type": "view",
                "full_name": s.name,
            }
            for s in self._get_sources()
        ]

    def get_columns(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
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

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        result = conn.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}')
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            result = conn.execute(sql)
        except (duckdb.CatalogException, duckdb.BinderException, duckdb.ParserException) as exc:
            raise DatabaseError(str(exc)) from exc
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]
