"""File connector — queries local CSV, Parquet, and JSON files via DuckDB."""

from __future__ import annotations

import glob as globmod
from dataclasses import dataclass, field
from typing import Any

from db_mcp_data.db.duckdb import (  # noqa: F401
    _FORMAT_MAP,
    DuckDBExecutor,
    _read_function_for_path,
)

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
    profile: str = ""
    sources: list[FileSourceConfig] = field(default_factory=list)
    directory: str = ""
    description: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

_SUPPORTED_EXTENSIONS = set(_FORMAT_MAP.keys())


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


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class FileConnector:
    """Connector that queries local files via an in-memory DuckDB instance."""

    def __init__(self, config: FileConnectorConfig) -> None:
        self.config = config
        self._resolved_sources: list[FileSourceConfig] | None = None
        self._duckdb = DuckDBExecutor(self._get_sources)

    def _get_sources(self) -> list[FileSourceConfig]:
        """Return all sources: explicit + discovered from directory."""
        if self._resolved_sources is None:
            sources = list(self.config.sources)
            if self.config.directory:
                sources.extend(_discover_directory(self.config.directory))
            self._resolved_sources = sources
        return self._resolved_sources

    def invalidate_cache(self) -> None:
        """Clear resolved sources and DuckDB connection so the next query re-discovers files."""
        self._resolved_sources = None
        self._duckdb.invalidate()

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
        return self._duckdb.get_columns(table_name)

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self._duckdb.get_table_sample(table_name, limit)

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        return self._duckdb.execute_sql(sql)
