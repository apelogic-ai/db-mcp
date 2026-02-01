"""API connector — fetches REST API data into JSONL, queries via DuckDB."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from db_mcp.connectors.file import FileConnector, FileConnectorConfig

# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class APIEndpointConfig:
    """A single API endpoint (maps to one table)."""

    name: str
    path: str
    method: str = "GET"


@dataclass
class APIPaginationConfig:
    """Pagination strategy for API requests."""

    type: str = "none"  # cursor | offset | link_header | none
    cursor_param: str = "starting_after"
    cursor_field: str = "data[-1].id"
    page_size_param: str = "limit"
    page_size: int = 100
    data_field: str = "data"  # JSON path to array of results


@dataclass
class APIAuthConfig:
    """Authentication configuration."""

    type: str = "bearer"  # bearer | header | query_param
    token_env: str = ""  # env var name for the token
    header_name: str = "Authorization"
    param_name: str = "api_key"


@dataclass
class APIConnectorConfig:
    """Configuration for the API connector."""

    type: str = field(default="api", init=False)
    base_url: str = ""
    auth: APIAuthConfig = field(default_factory=APIAuthConfig)
    endpoints: list[APIEndpointConfig] = field(default_factory=list)
    pagination: APIPaginationConfig = field(default_factory=APIPaginationConfig)
    rate_limit_rps: float = 10.0


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class APIConnector(FileConnector):
    """API connector — fetches REST API data into JSONL, queries via DuckDB.

    Inherits all query capabilities from FileConnector. After sync(),
    the data directory contains JSONL files that DuckDB queries directly.
    """

    def __init__(
        self,
        api_config: APIConnectorConfig,
        data_dir: str,
        env_path: str | None = None,
    ) -> None:
        self.api_config = api_config
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._env_path = env_path

        # Build FileConnectorConfig pointing to the data directory
        file_config = FileConnectorConfig(directory=str(self._data_dir))
        super().__init__(file_config)

    # -- Auth ---------------------------------------------------------------

    def _load_env(self) -> dict[str, str]:
        """Load environment variables from .env file."""
        env: dict[str, str] = {}
        if self._env_path:
            env_path = Path(self._env_path)
        else:
            # Default: .env in parent of data_dir (connection directory)
            env_path = self._data_dir.parent / ".env"

        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
        return env

    def _resolve_auth_headers(self) -> dict[str, str]:
        """Build auth headers from config + .env."""
        env = self._load_env()
        token_env = self.api_config.auth.token_env

        if token_env and token_env not in env:
            raise ValueError(
                f"Auth token env var '{token_env}' not found in .env file. "
                f"Add {token_env}=<your-token> to your .env file."
            )

        token = env.get(token_env, "")
        auth_type = self.api_config.auth.type

        if auth_type == "bearer":
            return {"Authorization": f"Bearer {token}"}
        elif auth_type == "header":
            return {self.api_config.auth.header_name: token}
        elif auth_type == "query_param":
            # Query params handled in _build_params, not headers
            return {}
        else:
            return {}

    def _resolve_auth_params(self) -> dict[str, str]:
        """Build auth query params (for query_param auth type)."""
        if self.api_config.auth.type != "query_param":
            return {}
        env = self._load_env()
        token = env.get(self.api_config.auth.token_env, "")
        return {self.api_config.auth.param_name: token}

    # -- Test connection ----------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        """Test API connectivity by making a lightweight request."""
        if not self.api_config.base_url:
            return {
                "connected": False,
                "dialect": "duckdb",
                "error": "No base_url configured",
            }

        try:
            headers = self._resolve_auth_headers()
            params = self._resolve_auth_params()

            # Try the first endpoint with a small limit
            if self.api_config.endpoints:
                ep = self.api_config.endpoints[0]
                url = self.api_config.base_url.rstrip("/") + ep.path
                pg = self.api_config.pagination
                if pg.page_size_param:
                    params[pg.page_size_param] = "1"
            else:
                url = self.api_config.base_url

            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()

            return {
                "connected": True,
                "dialect": "duckdb",
                "endpoints": len(self.api_config.endpoints),
                "error": None,
            }
        except ValueError as exc:
            return {"connected": False, "dialect": "duckdb", "error": str(exc)}
        except Exception as exc:
            return {"connected": False, "dialect": "duckdb", "error": str(exc)}

    # -- Sync ---------------------------------------------------------------

    def sync(self, endpoint_name: str | None = None) -> dict[str, Any]:
        """Fetch data from API endpoints and write JSONL files.

        Args:
            endpoint_name: Sync specific endpoint, or all if None.

        Returns:
            {"synced": [...], "rows_fetched": {...}, "errors": [...]}
        """
        endpoints = self.api_config.endpoints
        if endpoint_name:
            endpoints = [ep for ep in endpoints if ep.name == endpoint_name]

        synced: list[str] = []
        rows_fetched: dict[str, int] = {}
        errors: list[str] = []

        for ep in endpoints:
            try:
                rows = self._fetch_endpoint(ep)
                self._write_jsonl(ep.name, rows)
                synced.append(ep.name)
                rows_fetched[ep.name] = len(rows)
            except Exception as exc:
                errors.append(f"{ep.name}: {exc}")

        # Invalidate cached DuckDB connection so views refresh
        self._conn = None
        self._resolved_sources = None

        return {
            "synced": synced,
            "rows_fetched": rows_fetched,
            "errors": errors,
        }

    def _fetch_endpoint(self, endpoint: APIEndpointConfig) -> list[dict]:
        """Fetch all data from an endpoint, handling pagination."""
        headers = self._resolve_auth_headers()
        base_params = self._resolve_auth_params()
        url = self.api_config.base_url.rstrip("/") + endpoint.path
        pg = self.api_config.pagination

        if pg.type == "none":
            return self._fetch_single(url, headers, base_params)
        elif pg.type == "cursor":
            return self._fetch_cursor(url, headers, base_params, pg)
        elif pg.type == "offset":
            return self._fetch_offset(url, headers, base_params, pg)
        else:
            return self._fetch_single(url, headers, base_params)

    def _fetch_single(self, url: str, headers: dict, params: dict) -> list[dict]:
        """Fetch a single page (no pagination)."""
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        data_field = self.api_config.pagination.data_field
        if isinstance(body, list):
            return body
        return body.get(data_field, body.get("results", []))

    def _fetch_cursor(
        self,
        url: str,
        headers: dict,
        base_params: dict,
        pg: APIPaginationConfig,
    ) -> list[dict]:
        """Fetch all pages using cursor-based pagination."""
        all_rows: list[dict] = []
        params = dict(base_params)
        if pg.page_size_param:
            params[pg.page_size_param] = str(pg.page_size)

        while True:
            self._rate_limit()
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = body.get(pg.data_field, [])
            all_rows.extend(data)

            # Check if there are more pages
            has_more = body.get("has_more", False)
            if not has_more or not data:
                break

            # Extract cursor value from last item
            cursor_value = self._extract_cursor(data, pg.cursor_field)
            if cursor_value is None:
                break
            params[pg.cursor_param] = cursor_value

        return all_rows

    def _fetch_offset(
        self,
        url: str,
        headers: dict,
        base_params: dict,
        pg: APIPaginationConfig,
    ) -> list[dict]:
        """Fetch all pages using offset-based pagination."""
        all_rows: list[dict] = []
        offset = 0
        params = dict(base_params)
        if pg.page_size_param:
            params[pg.page_size_param] = str(pg.page_size)

        while True:
            self._rate_limit()
            params["offset"] = str(offset)
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = body.get(pg.data_field, [])
            if not data:
                break

            all_rows.extend(data)
            offset += len(data)

            if len(data) < pg.page_size:
                break

        return all_rows

    @staticmethod
    def _extract_cursor(data: list[dict], cursor_field: str) -> str | None:
        """Extract cursor value from data using a simple field path.

        Supports:
          - "data[-1].id" → last item's "id" field
          - "id" → last item's "id" field (shorthand)
        """
        if not data:
            return None

        # Always use the last item
        item = data[-1]

        # Strip any array prefix like "data[-1]."
        field = cursor_field
        if "." in field:
            field = field.rsplit(".", 1)[-1]

        value = item.get(field)
        return str(value) if value is not None else None

    def _rate_limit(self) -> None:
        """Simple rate limiting between requests."""
        if self.api_config.rate_limit_rps > 0:
            delay = 1.0 / self.api_config.rate_limit_rps
            time.sleep(delay)

    def _write_jsonl(self, name: str, rows: list[dict]) -> None:
        """Write rows as JSONL to the data directory."""
        path = self._data_dir / f"{name}.jsonl"
        with open(path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, default=str) + "\n")
