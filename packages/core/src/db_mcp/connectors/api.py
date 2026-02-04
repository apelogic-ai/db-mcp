"""API connector — fetches REST API data into JSONL, queries via DuckDB."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import yaml

from db_mcp.connectors.file import FileConnector, FileConnectorConfig

# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class APIQueryParamConfig:
    """Metadata for a query parameter accepted by an API endpoint."""

    name: str
    type: str = "string"  # string, integer, number, boolean
    description: str = ""
    required: bool = False
    enum: list[str] | None = None
    default: str | None = None


@dataclass
class APIEndpointConfig:
    """A single API endpoint (maps to one table)."""

    name: str
    path: str
    method: str = "GET"
    query_params: list[APIQueryParamConfig] = field(default_factory=list)
    body_mode: str = "query"  # query | json
    response_mode: str = "data"  # data | raw
    sql_field: str = "sql"  # Field name for SQL in execute_sql endpoints


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
    capabilities: dict[str, Any] = field(default_factory=dict)
    api_title: str = ""  # Display name from discovery (e.g., "Dune Analytics API")
    api_description: str = ""  # Description from API spec


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
                "dialect": self.api_config.api_title or "duckdb",
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
                "dialect": self.api_config.api_title or "duckdb",
                "endpoints": len(self.api_config.endpoints),
                "error": None,
            }
        except ValueError as exc:
            return {
                "connected": False,
                "dialect": self.api_config.api_title or "duckdb",
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "connected": False,
                "dialect": self.api_config.api_title or "duckdb",
                "error": str(exc),
            }

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
        if endpoint.method.upper() != "GET":
            raise ValueError("sync only supports GET endpoints")
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

    # -- Ad-hoc querying ----------------------------------------------------

    def query_endpoint(
        self,
        endpoint_name: str,
        params: dict[str, str] | None = None,
        max_pages: int = 1,
        id: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """Query an API endpoint directly with params, return results.

        Args:
            endpoint_name: Name of the configured endpoint to query.
            params: Query parameters to pass to the endpoint.
            max_pages: Maximum number of pages to fetch (default 1).
            id: Fetch specific record(s) by ID. Appends /{id} to endpoint path.
                Pass a single string or a list of strings for multiple records.

        Returns:
            {data: [...], rows_returned: int}
            or {error: "..."} on failure.
        """
        # Look up endpoint by name
        endpoint = None
        for ep in self.api_config.endpoints:
            if ep.name == endpoint_name:
                endpoint = ep
                break
        if endpoint is None:
            return {"error": f"Unknown endpoint: {endpoint_name}"}

        try:
            headers = self._resolve_auth_headers()
            base_params = self._resolve_auth_params()

            # Merge user params
            merged_params = dict(base_params)
            if params:
                merged_params.update(params)

            rendered_path, merged_params = self._render_path(endpoint.path, merged_params)
            base_url = self.api_config.base_url.rstrip("/") + rendered_path

            method = endpoint.method.upper()

            # Detail endpoint: fetch by ID(s)
            if id is not None:
                if method != "GET":
                    return {"error": "id lookup only supported for GET endpoints"}
                ids = [id] if isinstance(id, str) else id
                rows = self._fetch_by_ids(base_url, headers, merged_params, ids)
            elif method == "GET":
                rows = self._fetch_with_pagination(base_url, headers, merged_params, max_pages)
            else:
                rows = self._fetch_non_get(base_url, headers, merged_params, endpoint)

            return {
                "data": rows,
                "rows_returned": len(rows),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # -- SQL-like API execution ---------------------------------------------

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Execute SQL via API for SQL-like connectors.

        For connectors with supports_sql=true and sql_mode=api_sync, this method
        sends SQL to the configured execute_sql endpoint and returns results.

        Supports both sync and async APIs:
        - Sync: POST SQL, get results directly
        - Async: POST SQL, get execution_id, poll for results

        Args:
            sql: SQL query to execute
            params: Optional parameters (unused for most SQL APIs)

        Returns:
            List of row dicts

        Raises:
            ValueError: If SQL execution is not supported or fails
        """
        caps = self.api_config.capabilities
        if not caps.get("supports_sql"):
            # Fall back to parent's DuckDB-based execute_sql
            return super().execute_sql(sql, params)

        # Find the execute_sql endpoint
        execute_endpoint = None
        for ep in self.api_config.endpoints:
            if ep.name == "execute_sql":
                execute_endpoint = ep
                break

        if execute_endpoint is None:
            raise ValueError(
                "No 'execute_sql' endpoint configured. "
                "Add an endpoint named 'execute_sql' to connector.yaml."
            )

        headers = self._resolve_auth_headers()

        # Build the request
        url = self.api_config.base_url.rstrip("/") + execute_endpoint.path

        # Use configured field name for SQL (default: "sql")
        sql_field = execute_endpoint.sql_field or "sql"

        if execute_endpoint.body_mode == "json":
            body = {sql_field: sql}
            resp = requests.post(url, headers=headers, json=body, timeout=60)
        else:
            resp = requests.post(url, headers=headers, params={sql_field: sql}, timeout=60)

        resp.raise_for_status()
        result = resp.json()

        # Check if this is an async API (returns execution_id)
        execution_id = result.get("execution_id")
        if execution_id:
            return self._poll_execution_results(execution_id, headers)

        # Sync API - results are in the response
        return self._extract_rows_from_response(result)

    def _poll_execution_results(
        self,
        execution_id: str,
        headers: dict[str, str],
        max_wait_seconds: int = 300,
        poll_interval: float = 2.0,
    ) -> list[dict[str, Any]]:
        """Poll for async SQL execution results.

        Args:
            execution_id: The execution ID returned by execute_sql
            headers: Auth headers
            max_wait_seconds: Maximum time to wait for results
            poll_interval: Seconds between polls

        Returns:
            List of row dicts

        Raises:
            TimeoutError: If execution doesn't complete in time
            ValueError: If execution fails
        """
        # Find status and results endpoints
        status_endpoint = None
        results_endpoint = None
        for ep in self.api_config.endpoints:
            if ep.name == "execution_status":
                status_endpoint = ep
            elif ep.name == "execution_results":
                results_endpoint = ep

        if results_endpoint is None:
            raise ValueError(
                "No 'execution_results' endpoint configured for async SQL API. "
                "Add an endpoint named 'execution_results' to connector.yaml."
            )

        base_url = self.api_config.base_url.rstrip("/")
        start_time = time.time()

        while (time.time() - start_time) < max_wait_seconds:
            self._rate_limit()

            # Check status if endpoint exists
            if status_endpoint:
                status_path = status_endpoint.path.replace("{execution_id}", execution_id)
                status_url = base_url + status_path
                status_resp = requests.get(status_url, headers=headers, timeout=30)
                status_resp.raise_for_status()
                status_data = status_resp.json()

                state = status_data.get("state", "").lower()
                # Also check is_execution_finished for APIs like Dune
                is_finished = status_data.get("is_execution_finished", False)

                if "failed" in state or "error" in state or "cancelled" in state:
                    error_msg = status_data.get("error", "Execution failed")
                    raise ValueError(f"SQL execution failed: {error_msg}")

                # Check for completion - handle various formats like "QUERY_STATE_COMPLETED"
                is_complete = (
                    is_finished or "complete" in state or "success" in state or "finished" in state
                )
                if not is_complete:
                    time.sleep(poll_interval)
                    continue

            # Fetch results
            results_path = results_endpoint.path.replace("{execution_id}", execution_id)
            results_url = base_url + results_path
            results_resp = requests.get(results_url, headers=headers, timeout=60)
            results_resp.raise_for_status()
            results_data = results_resp.json()

            return self._extract_rows_from_response(results_data)

        raise TimeoutError(f"SQL execution did not complete within {max_wait_seconds} seconds")

    def _extract_rows_from_response(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract rows from an API response.

        Handles common response formats:
        - {result: {rows: [...]}} (Dune)
        - {data: [...]}
        - {rows: [...]}
        - {results: [...]}
        - Direct list

        Args:
            response: API response dict

        Returns:
            List of row dicts
        """
        if isinstance(response, list):
            return response

        # Try nested result.rows (Dune format)
        result = response.get("result", {})
        if isinstance(result, dict):
            rows = result.get("rows")
            if rows is not None:
                return rows if isinstance(rows, list) else []

        # Check for columns + rows as arrays format first (before generic field check)
        # This handles APIs that return {columns: [...], rows: [[...], [...]]}
        columns = response.get("columns") or response.get("column_names")
        rows_data = response.get("rows") or response.get("data")
        if (
            columns
            and rows_data
            and isinstance(rows_data, list)
            and rows_data
            and isinstance(rows_data[0], list)
        ):
            # Rows are arrays, need to zip with column names
            return [dict(zip(columns, row)) for row in rows_data]

        # Try common top-level fields (rows are already dicts)
        for field_name in ("rows", "data", "results", "records"):
            if field_name in response:
                value = response[field_name]
                if isinstance(value, list):
                    return value

        # Last resort: return empty
        return []

    @staticmethod
    def _render_path(path: str, params: dict[str, str]) -> tuple[str, dict[str, str]]:
        """Substitute {param} placeholders in a path using params."""
        remaining = dict(params)

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in remaining:
                raise ValueError(f"Missing path param: {key}")
            return str(remaining.pop(key))

        rendered = re.sub(r"\{(\w+)\}", repl, path)
        return rendered, remaining

    def _fetch_non_get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        endpoint: APIEndpointConfig,
    ) -> list[dict]:
        """Execute non-GET requests and return rows."""
        if endpoint.response_mode == "raw":
            body = self._send_non_get(url, headers, params, endpoint)
            return body

        body = self._send_non_get(url, headers, params, endpoint)
        if isinstance(body, list):
            return body
        data_field = self.api_config.pagination.data_field
        return body.get(data_field, body.get("results", []))

    def _send_non_get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        endpoint: APIEndpointConfig,
    ) -> Any:
        """Send a non-GET request and return the raw JSON body."""
        if endpoint.body_mode == "json":
            resp = requests.post(url, headers=headers, json=params, params={}, timeout=30)
        else:
            resp = requests.post(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _fetch_by_ids(
        self,
        base_url: str,
        headers: dict[str, str],
        params: dict[str, str],
        ids: list[str],
    ) -> list[dict]:
        """Fetch individual records by ID from detail endpoints."""
        rows: list[dict] = []
        for record_id in ids:
            self._rate_limit()
            url = base_url.rstrip("/") + "/" + str(record_id)
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, dict):
                rows.append(body)
            elif isinstance(body, list):
                rows.extend(body)
        return rows

    def _fetch_with_pagination(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        max_pages: int,
    ) -> list[dict]:
        """Fetch data from a URL, handling pagination up to max_pages."""
        pg = self.api_config.pagination

        if pg.type == "none":
            return self._fetch_single(url, headers, params)

        if pg.type == "cursor":
            return self._fetch_cursor_paged(url, headers, params, pg, max_pages)

        if pg.type == "offset":
            return self._fetch_offset_paged(url, headers, params, pg, max_pages)

        # Fallback: single fetch
        return self._fetch_single(url, headers, params)

    def _fetch_cursor_paged(
        self,
        url: str,
        headers: dict[str, str],
        base_params: dict[str, str],
        pg: APIPaginationConfig,
        max_pages: int,
    ) -> list[dict]:
        """Fetch pages using cursor pagination with a page cap."""
        all_rows: list[dict] = []
        params = dict(base_params)
        if pg.page_size_param:
            params[pg.page_size_param] = str(pg.page_size)

        for _ in range(max_pages):
            self._rate_limit()
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()

            if isinstance(body, list):
                data = body
            else:
                data = body.get(pg.data_field, [])
            all_rows.extend(data)

            # Check if there are more pages
            has_more = body.get("has_more", False) if isinstance(body, dict) else False
            if not has_more or not data:
                break

            cursor_value = self._extract_cursor(data, pg.cursor_field)
            if cursor_value is None:
                break
            params[pg.cursor_param] = cursor_value

        return all_rows

    def _fetch_offset_paged(
        self,
        url: str,
        headers: dict[str, str],
        base_params: dict[str, str],
        pg: APIPaginationConfig,
        max_pages: int,
    ) -> list[dict]:
        """Fetch pages using offset pagination with a page cap."""
        all_rows: list[dict] = []
        offset = 0
        params = dict(base_params)
        if pg.page_size_param:
            params[pg.page_size_param] = str(pg.page_size)

        for _ in range(max_pages):
            self._rate_limit()
            params["offset"] = str(offset)
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = body.get(pg.data_field, []) if isinstance(body, dict) else body
            if not data:
                break

            all_rows.extend(data)
            offset += len(data)

            if len(data) < pg.page_size:
                break

        return all_rows

    # -- Discovery ----------------------------------------------------------

    def discover(self) -> dict[str, Any]:
        """Discover API endpoints, pagination, and schema.

        Uses the three-stage discovery pipeline from api_discovery module.
        Updates self.api_config with discovered endpoints and pagination.

        Returns:
            Dict with discovery results including endpoints found and strategy used.
        """
        from db_mcp.connectors.api_discovery import discover_api

        try:
            auth_headers = self._resolve_auth_headers()
        except ValueError:
            auth_headers = {}
        auth_params = self._resolve_auth_params()

        result = discover_api(
            base_url=self.api_config.base_url,
            auth_headers=auth_headers,
            auth_params=auth_params,
            rate_limit_rps=self.api_config.rate_limit_rps,
        )

        # Update config with discovered endpoints
        if result.endpoints:
            self.api_config.endpoints = [
                APIEndpointConfig(
                    name=ep.name,
                    path=ep.path,
                    method=ep.method,
                    query_params=[
                        APIQueryParamConfig(
                            name=qp.name,
                            type=qp.type,
                            description=qp.description,
                            required=qp.required,
                            enum=qp.enum,
                            default=qp.default,
                        )
                        for qp in ep.query_params
                    ],
                )
                for ep in result.endpoints
            ]

        # Update pagination if discovered
        if result.pagination.type != "none":
            self.api_config.pagination = APIPaginationConfig(
                type=result.pagination.type,
                cursor_param=result.pagination.cursor_param or "starting_after",
                cursor_field=result.pagination.cursor_field or "data[-1].id",
                page_size_param=result.pagination.page_size_param or "limit",
                page_size=result.pagination.page_size,
                data_field=result.pagination.data_field or "data",
            )

        # Store API title and description
        if result.api_title:
            self.api_config.api_title = result.api_title
        if result.api_description:
            self.api_config.api_description = result.api_description

        return {
            "strategy": result.strategy,
            "spec_url": result.spec_url,
            "api_title": result.api_title,
            "api_description": result.api_description,
            "endpoints_found": len(result.endpoints),
            "endpoints": [
                {"name": ep.name, "path": ep.path, "fields": len(ep.fields)}
                for ep in result.endpoints
            ],
            "pagination": {
                "type": result.pagination.type,
                "data_field": result.pagination.data_field,
            },
            "errors": result.errors,
        }

    def save_connector_yaml(self, yaml_path: str | Path) -> None:
        """Save current api_config to a connector.yaml file.

        Args:
            yaml_path: Path to write the connector.yaml file.
        """
        data: dict[str, Any] = {
            "type": "api",
            "base_url": self.api_config.base_url,
        }

        # Add optional API metadata
        if self.api_config.api_title:
            data["api_title"] = self.api_config.api_title
        if self.api_config.api_description:
            data["api_description"] = self.api_config.api_description

        data.update(
            {
                "auth": {
                    "type": self.api_config.auth.type,
                    "token_env": self.api_config.auth.token_env,
                    "header_name": self.api_config.auth.header_name,
                    "param_name": self.api_config.auth.param_name,
                },
                "endpoints": [
                    {
                        "name": ep.name,
                        "path": ep.path,
                        "method": ep.method,
                        "body_mode": ep.body_mode,
                        "response_mode": ep.response_mode,
                        **({"sql_field": ep.sql_field} if ep.sql_field != "sql" else {}),
                        **(
                            {
                                "query_params": [
                                    {
                                        k: v
                                        for k, v in {
                                            "name": qp.name,
                                            "type": qp.type,
                                            "description": qp.description,
                                            "required": qp.required or None,
                                            "enum": qp.enum,
                                            "default": qp.default,
                                        }.items()
                                        if v
                                    }
                                    for qp in ep.query_params
                                ]
                            }
                            if ep.query_params
                            else {}
                        ),
                    }
                    for ep in self.api_config.endpoints
                ],
                "pagination": {
                    "type": self.api_config.pagination.type,
                    "cursor_param": self.api_config.pagination.cursor_param,
                    "cursor_field": self.api_config.pagination.cursor_field,
                    "page_size_param": self.api_config.pagination.page_size_param,
                    "page_size": self.api_config.pagination.page_size,
                    "data_field": self.api_config.pagination.data_field,
                },
                "rate_limit": {
                    "requests_per_second": self.api_config.rate_limit_rps,
                },
            }
        )

        if self.api_config.capabilities:
            data["capabilities"] = self.api_config.capabilities

        path = Path(yaml_path)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
