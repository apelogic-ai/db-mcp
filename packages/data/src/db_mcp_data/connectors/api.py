"""API connector — fetches REST API data into JSONL, queries via DuckDB."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests
import yaml

from db_mcp_data.connector_plugins.compat import normalize_connector_payload
from db_mcp_data.connectors import api_auth as _api_auth
from db_mcp_data.connectors import api_pagination as _api_pg
from db_mcp_data.connectors.api_config import (
    APIAuthConfig,
    APIConnectorConfig,
    APIEndpointConfig,
    APIPaginationConfig,
    APIQueryParamConfig,
    build_api_connector_config,
)
from db_mcp_data.connectors.api_discovery import discover_api, discover_openapi_spec
from db_mcp_data.connectors.api_schema import map_schema_type as _schema_map_type
from db_mcp_data.connectors.file import FileConnector, FileConnectorConfig
from db_mcp_data.contracts.connector_contracts import CONNECTOR_SPEC_VERSION

# Re-export config types so existing callers importing from this module continue to work.
__all__ = [
    "APIAuthConfig",
    "APIConnectorConfig",
    "APIEndpointConfig",
    "APIPaginationConfig",
    "APIQueryParamConfig",
    "build_api_connector_config",
    "APIConnector",
]

# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class APIConnector:
    """API connector — fetches REST API data into JSONL, queries via DuckDB.

    Uses FileConnector internally for all DuckDB query capabilities. After sync(),
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
        self._jwt_token: str | None = None
        self._jwt_expires: float = 0.0
        self._schema_cache: list[dict[str, Any]] | None = None

        # Delegate DuckDB query capabilities to an internal FileConnector
        file_config = FileConnectorConfig(directory=str(self._data_dir))
        self._file_connector = FileConnector(file_config)

    @staticmethod
    def _format_api_error(error: Any, default: str) -> str:
        """Convert structured API error payloads into readable messages."""
        if isinstance(error, dict):
            for key in ("message", "detail", "error", "reason"):
                value = error.get(key)
                if value:
                    return str(value)
            return str(error)
        if error:
            return str(error)
        return default

    def _extract_response_error(self, response: dict[str, Any]) -> str | None:
        """Extract execution failure details from API status/result payloads."""
        state = str(response.get("state") or response.get("status") or "").lower()
        error = response.get("error")
        is_failed_state = any(token in state for token in ("failed", "error", "cancelled"))
        if is_failed_state:
            return self._format_api_error(error, f"Execution failed ({state})")
        if error and response.get("success") is False:
            return self._format_api_error(error, "API request failed")
        return None

    # -- Auth ---------------------------------------------------------------

    def _load_env(self) -> dict[str, str]:
        """Load environment variables from .env file."""
        return _api_auth.load_env(self._env_path, self._data_dir)

    def _resolve_auth_headers(self) -> dict[str, str]:
        """Build auth headers from config + .env."""

        def _login_fn() -> str:
            self._jwt_login()
            return self._jwt_token  # type: ignore[return-value]

        return _api_auth.resolve_auth_headers(
            self.api_config, self._env_path, self._data_dir, self._jwt_token, _login_fn
        )

    def _resolve_basic_credentials(self) -> tuple[str, str]:
        """Resolve username/password for basic auth from env or literal aliases."""
        return _api_auth.resolve_basic_credentials(
            self.api_config.auth, self._env_path, self._data_dir
        )

    def _jwt_login(self) -> None:
        """Perform JWT login: POST creds to login endpoint, cache token."""
        token, expires_at = _api_auth.jwt_login(self.api_config, self._env_path, self._data_dir)
        self._jwt_token = token
        self._jwt_expires = expires_at

    def _jwt_refresh(self) -> None:
        """Force refresh JWT token by re-logging in."""
        self._jwt_token = None
        self._jwt_expires = 0.0
        self._jwt_login()

    def _resolve_auth_params(self) -> dict[str, str]:
        """Build auth query params (for query_param auth type)."""
        return _api_auth.resolve_auth_params(self.api_config, self._env_path, self._data_dir)

    def _runtime_path_params(self, path: str | None = None) -> dict[str, str]:
        return {}

    def _runtime_template_context(self) -> dict[str, Any]:
        return {}

    # -- Unified HTTP dispatch ----------------------------------------------

    def _send_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        query_params: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> Any:
        """Send an HTTP request using requests.request.

        GET: params as query string, no body.
        POST/PUT/PATCH/DELETE: body as JSON, params as query string.
        """
        kwargs: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "headers": headers,
            "params": query_params or {},
            "timeout": 30,
        }
        if body is not None:
            kwargs["json"] = body
        resp = requests.request(**kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_dialect(self) -> str:
        """Return dialect identifier (delegated to internal FileConnector)."""
        return self._file_connector.get_dialect()

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
            method = "GET"
            body: dict[str, Any] | None = None

            if self.api_config.endpoints:
                ep = self.api_config.endpoints[0]
                params.update(self._runtime_path_params(ep.path))
                rendered_path, params = self._render_path(ep.path, params)
                url = self.api_config.base_url.rstrip("/") + rendered_path
                method = (ep.method or "GET").upper()
                pg = self.api_config.pagination
                if method == "GET" and pg.type != "none" and pg.page_size_param:
                    params[pg.page_size_param] = "1"
                if method != "GET" and ep.name == "execute_sql":
                    if ep.body_template is not None:
                        _, body = self._build_execute_sql_request(
                            ep,
                            "SELECT 1 AS db_mcp_doctor",
                            self._runtime_template_context(),
                        )
                    else:
                        body = {ep.sql_field or "sql": "SELECT 1 AS db_mcp_doctor"}
            else:
                url = self.api_config.base_url

            request_kwargs: dict[str, Any] = {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": 10,
            }
            if body is not None:
                request_kwargs["json"] = body

            resp = requests.request(**request_kwargs)
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
            if not self.api_config.endpoints:
                spec, discovered_spec_url = discover_openapi_spec(
                    self.api_config.base_url,
                    headers,
                    self.api_config.rate_limit_rps,
                    spec_url=self.api_config.spec_url or None,
                )
                if spec is not None and discovered_spec_url:
                    return {
                        "connected": True,
                        "dialect": self.api_config.api_title or "duckdb",
                        "endpoints": 0,
                        "error": None,
                        "hint": (
                            "OpenAPI document reachable. Discovery will extract endpoints "
                            "and resolve the API base URL."
                        ),
                    }
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

        # Invalidate cached DuckDB connection so views refresh with new JSONL files
        self._file_connector.invalidate_cache()

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
        base_params.update(self._runtime_path_params(endpoint.path))
        rendered_path, base_params = self._render_path(endpoint.path, base_params)
        url = self.api_config.base_url.rstrip("/") + rendered_path
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
        if isinstance(body, list):
            return body
        if not isinstance(body, dict):
            return []

        error_msg = self._extract_response_error(body)
        if error_msg:
            raise ValueError(error_msg)

        extracted_rows = self._extract_response_rows(body, self.api_config.pagination)
        if extracted_rows:
            return extracted_rows

        # Keep flat JSON payloads (e.g. execution status) instead of dropping them.
        return [body]

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
            resp = requests.get(url, headers=headers, params=dict(params), timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = self._extract_response_rows(body, pg)
            all_rows.extend(data)

            # Check if there are more pages
            has_more = self._response_has_more(body, data, pg)
            if not has_more or not data:
                break

            cursor_value = self._extract_cursor_value(body, data, pg)
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
            params[pg.offset_param] = str(offset)
            resp = requests.get(url, headers=headers, params=dict(params), timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = self._extract_response_rows(body, pg)
            if not data:
                break

            all_rows.extend(data)
            offset += len(data)

            if len(data) < pg.page_size:
                break

        return all_rows

    @staticmethod
    def _extract_cursor(data: list[dict], cursor_field: str) -> str | None:
        """Extract cursor value from data using a simple field path."""
        return _api_pg.extract_cursor(data, cursor_field)

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

    @staticmethod
    def _get_nested_value(payload: Any, path: str) -> Any:
        """Resolve a dotted field path from a nested JSON-like payload."""
        return _api_pg.get_nested_value(payload, path)

    @staticmethod
    def _normalize_column_names(columns: list[Any]) -> list[str]:
        """Normalize column descriptors into a list of output field names."""
        return _api_pg.normalize_column_names(columns)

    @classmethod
    def _rows_from_columnar_payload(
        cls,
        columns: Any,
        rows_data: Any,
    ) -> list[dict[str, Any]]:
        """Convert column names plus row arrays into row dicts."""
        return _api_pg.rows_from_columnar_payload(columns, rows_data)

    @classmethod
    def _render_template_value(cls, value: Any, context: dict[str, Any]) -> Any:
        """Recursively render ``{{key}}`` placeholders inside a JSON-compatible value."""
        return _api_pg.render_template_value(value, context)

    def _extract_response_rows(
        self,
        response: Any,
        pagination: APIPaginationConfig | None = None,
    ) -> list[dict[str, Any]]:
        """Extract rows using connector pagination hints plus common API wrappers."""
        if isinstance(response, list):
            return response
        if not isinstance(response, dict):
            return []

        data_field = pagination.data_field if pagination else ""
        if data_field:
            value = self._get_nested_value(response, data_field)
            if isinstance(value, list):
                return value

        return self._extract_rows_from_response(response)

    def _response_has_more(
        self,
        response: Any,
        rows: list[dict[str, Any]],
        pagination: APIPaginationConfig,
    ) -> bool:
        """Detect whether a paginated response has more data."""
        if not isinstance(response, dict):
            return False

        if "has_more" in response:
            return bool(response.get("has_more"))
        if "hasMore" in response:
            return bool(response.get("hasMore"))
        if "isLast" in response:
            return not bool(response.get("isLast"))

        cursor_value = self._extract_cursor_value(response, rows, pagination)
        return cursor_value is not None

    def _extract_cursor_value(
        self,
        response: Any,
        rows: list[dict[str, Any]],
        pagination: APIPaginationConfig,
    ) -> str | None:
        """Extract the next cursor token from a response or the last row."""
        if isinstance(response, dict):
            direct_candidates = [
                pagination.cursor_field,
                pagination.cursor_param,
                "nextPageToken",
                "next_cursor",
                "next",
                "starting_after",
                "cursor",
                "next_token",
                "after",
            ]
            for candidate in direct_candidates:
                if not candidate:
                    continue
                if "." in candidate or "[" in candidate:
                    continue
                value = response.get(candidate)
                if value is not None and value != "":
                    return str(value)

        return self._extract_cursor(rows, pagination.cursor_field)

    # -- Ad-hoc querying ----------------------------------------------------

    def query_endpoint(
        self,
        endpoint_name: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 1,
        id: str | list[str] | None = None,
        body: dict[str, Any] | None = None,
        method_override: str | None = None,
    ) -> dict[str, Any]:
        """Query an API endpoint directly with params, return results.

        Args:
            endpoint_name: Name of the configured endpoint to query.
            params: Parameters to pass to the endpoint. For GET these are query
                parameters; for many write endpoints these may be promoted to a
                JSON body when no explicit body is provided.
            max_pages: Maximum number of pages to fetch (default 1).
            id: Fetch specific record(s) by ID. Appends /{id} to endpoint path.
                Pass a single string or a list of strings for multiple records.
            body: JSON request body for POST/PUT/PATCH requests.
            method_override: Override the endpoint's default HTTP method.

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
            base_params.update(self._runtime_path_params(endpoint.path))
            method = (method_override or endpoint.method).upper()

            # Merge user params
            merged_params = dict(base_params)
            if params:
                merged_params.update(params)

            # If endpoint path is templated with {id}, allow id argument to fill it
            # for both read and write methods.
            if id is not None and "{id}" in endpoint.path:
                if isinstance(id, list):
                    return {
                        "error": "id must be a single value when endpoint path contains {id}"
                    }
                merged_params["id"] = id

            rendered_path, merged_params = self._render_path(endpoint.path, merged_params)
            base_url = self.api_config.base_url.rstrip("/") + rendered_path

            # Detail endpoint: fetch by ID(s)
            if id is not None:
                if method == "GET":
                    # If endpoint template consumed {id}, query the already rendered URL.
                    if "{id}" in endpoint.path:
                        raw = self._send_request_with_retry(
                            method, base_url, headers, merged_params, body
                        )
                        if endpoint.response_mode == "raw":
                            return {"data": raw, "rows_returned": 1}
                        rows = self._extract_rows_from_response(raw)
                    else:
                        ids = [id] if isinstance(id, str) else id
                        rows = self._fetch_by_ids(base_url, headers, merged_params, ids)
                elif "{id}" in endpoint.path:
                    # Non-GET method with templated path: continue through write flow.
                    pass
                else:
                    return {"error": "id lookup only supported for GET endpoints or {id} paths"}
            elif method == "GET":
                if endpoint.response_mode == "raw":
                    raw = self._send_request_with_retry(
                        method, base_url, headers, merged_params, body
                    )
                    return {"data": raw, "rows_returned": 1}
                rows = self._fetch_with_pagination(base_url, headers, merged_params, max_pages)
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                # Determine the effective JSON body:
                # - Explicit body parameter takes priority
                # - Backward compat: body_mode=json with no explicit body → params as body
                effective_body = body
                effective_params = merged_params
                if effective_body is None and endpoint.body_mode == "json":
                    effective_body = merged_params
                    effective_params = {}
                elif effective_body is None and params and not endpoint.query_params:
                    # Heuristic for write APIs: if the endpoint declares no query
                    # params, treat user-supplied params as a JSON body.
                    user_payload = dict(merged_params)
                    for key, value in base_params.items():
                        if user_payload.get(key) == value:
                            user_payload.pop(key, None)
                    if user_payload:
                        effective_body = user_payload
                        effective_params = dict(base_params)

                raw = self._send_request_with_retry(
                    method, base_url, headers, effective_params, effective_body
                )
                if endpoint.response_mode == "raw":
                    return {"data": raw, "rows_returned": 1}
                rows = self._extract_rows_from_response(raw)
                if not rows and isinstance(raw, dict):
                    # Preserve prior behavior for single-object create/update responses.
                    rows = [raw]
            elif method not in ("GET",):
                rows = self._fetch_non_get(base_url, headers, merged_params, endpoint)

            return {
                "data": rows,
                "rows_returned": len(rows) if isinstance(rows, list) else 1,
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _send_request_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        query_params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Send request with automatic login-token 401 retry."""
        try:
            return self._send_request(method, url, headers, query_params, body)
        except requests.exceptions.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.status_code == 401
                and self.api_config.auth.type in {"jwt_login", "login"}
            ):
                self._jwt_token = None
                self._jwt_login()
                headers = self._resolve_auth_headers()
                return self._send_request(method, url, headers, query_params, body)
            raise

    # -- SQL-like API execution ---------------------------------------------

    def _get_endpoint(self, name: str) -> APIEndpointConfig | None:
        for endpoint in self.api_config.endpoints:
            if endpoint.name == name:
                return endpoint
        return None

    def _build_execute_sql_request(
        self,
        endpoint: APIEndpointConfig,
        sql: str,
        template_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build query params and JSON body for a configured SQL execution endpoint."""
        context = {"sql": sql}
        if template_context:
            context.update(template_context)
        if endpoint.body_template is not None:
            body = self._render_template_value(endpoint.body_template, context)
            return {}, body

        sql_field = endpoint.sql_field or "sql"
        if endpoint.body_mode == "json":
            return {}, {sql_field: sql}
        return {sql_field: sql}, {}

    def submit_sql(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Submit SQL to an API execute endpoint.

        Returns:
            {"mode": "async", "execution_id": "..."} for async APIs
            {"mode": "sync", "rows": [...]} for APIs returning rows immediately
        """
        caps = self.api_config.capabilities
        supports_sql = caps.get("supports_sql")
        if supports_sql is None:
            supports_sql = caps.get("sql")
        if not supports_sql:
            rows = self._file_connector.execute_sql(sql, None)
            return {"mode": "sync", "rows": rows}

        execute_endpoint = self._get_endpoint("execute_sql")
        if execute_endpoint is None:
            raise ValueError(
                "No 'execute_sql' endpoint configured. "
                "Add an endpoint named 'execute_sql' to connector.yaml."
            )

        headers = self._resolve_auth_headers()
        runtime_context = self._runtime_template_context()

        runtime_params = self._runtime_path_params(execute_endpoint.path)
        rendered_path, runtime_params = self._render_path(execute_endpoint.path, runtime_params)
        url = self.api_config.base_url.rstrip("/") + rendered_path
        query_params, body = self._build_execute_sql_request(
            execute_endpoint,
            sql,
            runtime_context,
        )
        if body:
            body = {key: value for key, value in body.items() if value is not None}
        try:
            request_kwargs: dict[str, Any] = {"headers": headers, "timeout": 60}
            if query_params:
                request_kwargs["params"] = query_params
            if body:
                request_kwargs["json"] = body
            resp = requests.post(url, **request_kwargs)
            resp.raise_for_status()
            response = resp.json()
        except requests.exceptions.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.status_code == 401
                and self.api_config.auth.type in {"jwt_login", "login"}
            ):
                self._jwt_refresh()
                headers = self._resolve_auth_headers()
                request_kwargs = {"headers": headers, "timeout": 60}
                if query_params:
                    request_kwargs["params"] = query_params
                if body:
                    request_kwargs["json"] = body
                resp = requests.post(url, **request_kwargs)
                resp.raise_for_status()
                response = resp.json()
            else:
                raise

        if not isinstance(response, dict):
            rows = self._extract_rows_from_response({"rows": response})
            return {"mode": "sync", "rows": rows}

        execution_id = response.get("execution_id")
        if execution_id is None:
            execution_id = response.get("executionId")
        if execution_id is not None:
            return {
                "mode": "async",
                "execution_id": str(execution_id),
                "raw": response,
            }

        rows = self._extract_rows_from_response(response)
        return {"mode": "sync", "rows": rows, "raw": response}

    def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        """Get async execution status from API, if supported."""
        status_endpoint = self._get_endpoint("execution_status")
        if status_endpoint is None:
            return {
                "state": "UNKNOWN",
                "execution_id": execution_id,
                "status_endpoint": False,
            }

        headers = self._resolve_auth_headers()
        status_path = status_endpoint.path.replace("{execution_id}", execution_id)
        status_url = self.api_config.base_url.rstrip("/") + status_path
        try:
            status_resp = requests.get(status_url, headers=headers, timeout=30)
            status_resp.raise_for_status()
            status_data = status_resp.json()
        except requests.exceptions.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.status_code == 401
                and self.api_config.auth.type in {"jwt_login", "login"}
            ):
                self._jwt_refresh()
                headers = self._resolve_auth_headers()
                status_resp = requests.get(status_url, headers=headers, timeout=30)
                status_resp.raise_for_status()
                status_data = status_resp.json()
            else:
                raise
        if not isinstance(status_data, dict):
            return {
                "state": "UNKNOWN",
                "execution_id": execution_id,
                "raw": status_data,
                "status_endpoint": True,
            }
        return status_data

    def get_execution_results(self, execution_id: str) -> list[dict[str, Any]]:
        """Fetch async SQL execution results from API."""
        results_endpoint = self._get_endpoint("execution_results")
        if results_endpoint is None:
            raise ValueError(
                "No 'execution_results' endpoint configured for async SQL API. "
                "Add an endpoint named 'execution_results' to connector.yaml."
            )

        headers = self._resolve_auth_headers()
        results_path = results_endpoint.path.replace("{execution_id}", execution_id)
        results_url = self.api_config.base_url.rstrip("/") + results_path
        try:
            results_resp = requests.get(results_url, headers=headers, timeout=60)
            results_resp.raise_for_status()
            results_data = results_resp.json()
        except requests.exceptions.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.status_code == 401
                and self.api_config.auth.type in {"jwt_login", "login"}
            ):
                self._jwt_refresh()
                headers = self._resolve_auth_headers()
                results_resp = requests.get(results_url, headers=headers, timeout=60)
                results_resp.raise_for_status()
                results_data = results_resp.json()
            else:
                raise
        if isinstance(results_data, list):
            return results_data
        if not isinstance(results_data, dict):
            return []
        return self._extract_rows_from_response(results_data)

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
        submission = self.submit_sql(sql, params=params)
        if submission.get("mode") == "sync":
            rows = submission.get("rows", [])
            return rows if isinstance(rows, list) else []

        execution_id = submission.get("execution_id")
        if not execution_id:
            raise ValueError("SQL execution submission did not return execution_id")

        return self._poll_execution_results(str(execution_id))

    def _poll_execution_results(
        self,
        execution_id: str,
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
        status_endpoint = self._get_endpoint("execution_status")
        start_time = time.time()

        while (time.time() - start_time) < max_wait_seconds:
            self._rate_limit()

            # Check status if endpoint exists
            if status_endpoint:
                status_data = self.get_execution_status(execution_id)

                state = status_data.get("state", "").lower()
                # Some APIs expose an explicit completion boolean.
                is_finished = status_data.get("is_execution_finished", False)

                if "failed" in state or "error" in state or "cancelled" in state:
                    error_msg = self._format_api_error(
                        status_data.get("error"),
                        "Execution failed",
                    )
                    raise ValueError(f"SQL execution failed: {error_msg}")

                # Check for completion - handle various formats like "QUERY_STATE_COMPLETED"
                is_complete = (
                    is_finished or "complete" in state or "success" in state or "finished" in state
                )
                if not is_complete:
                    time.sleep(poll_interval)
                    continue

            try:
                return self.get_execution_results(execution_id)
            except requests.exceptions.HTTPError as exc:
                # Some APIs expose only results endpoint and return 404/409 while pending.
                if (
                    not status_endpoint
                    and exc.response is not None
                    and exc.response.status_code in (404, 409, 425)
                ):
                    time.sleep(poll_interval)
                    continue
                raise

        raise TimeoutError(f"SQL execution did not complete within {max_wait_seconds} seconds")

    def _get_schema_rows(self) -> list[dict[str, Any]] | None:
        """Return schema metadata rows when a connector declares a ``schema`` endpoint."""
        if self._schema_cache is not None:
            return self._schema_cache

        schema_endpoint = self._get_endpoint("schema")
        if schema_endpoint is None:
            return None

        result = self.query_endpoint("schema")
        if "error" in result:
            raise ValueError(result["error"])

        payload = result.get("data", [])
        if isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict):
            rows = self._extract_rows_from_response(payload)
        else:
            rows = []

        self._schema_cache = rows
        return self._schema_cache

    @staticmethod
    def _map_schema_type(base_type: str | None) -> str:
        """Best-effort type mapping for API schema metadata."""
        return _schema_map_type(base_type)

    def get_catalogs(self) -> list[str | None]:
        return self._file_connector.get_catalogs()

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        schema_rows = self._get_schema_rows()
        if schema_rows is None:
            return self._file_connector.get_schemas(catalog)

        schemas = {row.get("schema") for row in schema_rows if row.get("schema")}
        return sorted(schemas) if schemas else [None]

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        schema_rows = self._get_schema_rows()
        if schema_rows is None:
            return self._file_connector.get_tables(schema, catalog)

        tables: list[dict[str, Any]] = []
        catalog_name = self.get_catalogs()[0]
        for row in schema_rows:
            row_schema = row.get("schema")
            if schema and row_schema != schema:
                continue
            name = row.get("name")
            if not name:
                continue
            full_name = f"{row_schema}.{name}" if row_schema else str(name)
            tables.append(
                {
                    "name": name,
                    "schema": row_schema,
                    "catalog": catalog_name,
                    "type": "table",
                    "full_name": full_name,
                }
            )
        return tables

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        schema_rows = self._get_schema_rows()
        if schema_rows is None:
            return self._file_connector.get_columns(table_name, schema, catalog)

        for row in schema_rows:
            if row.get("name") != table_name:
                continue
            if schema and row.get("schema") != schema:
                continue
            fields = row.get("fields", []) or []
            return [
                {
                    "name": field.get("name"),
                    "type": self._map_schema_type(field.get("base_type")),
                    "nullable": True,
                    "default": None,
                    "primary_key": False,
                    "comment": None,
                }
                for field in fields
                if isinstance(field, dict) and field.get("name")
            ]

        return self._file_connector.get_columns(table_name, schema, catalog)

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if self._get_schema_rows() is None or self._get_endpoint("execute_sql") is None:
            return self._file_connector.get_table_sample(table_name, schema, catalog, limit)

        source = f"{schema}.{table_name}" if schema else table_name
        return self.execute_sql(f"SELECT * FROM {source} LIMIT {limit}")

    def _extract_rows_from_response(self, response: Any) -> list[dict[str, Any]]:
        """Extract rows from an API response.

        Handles common response formats:
        - {result: {rows: [...]}}
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

        # Try result wrappers first.
        result = response.get("result")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            rows = result.get("rows")
            if isinstance(rows, list):
                return rows

        # Check for columns + rows as arrays format first (before generic field check)
        # This handles APIs that return {columns: [...], rows: [[...], [...]]}
        columns = response.get("columns") or response.get("column_names")
        rows_data = response.get("rows") or response.get("data")
        columnar_rows = self._rows_from_columnar_payload(columns, rows_data)
        if columnar_rows:
            return columnar_rows

        nested_data = response.get("data")
        if isinstance(nested_data, dict):
            nested_columns = (
                nested_data.get("cols")
                or nested_data.get("columns")
                or nested_data.get("column_names")
            )
            nested_rows = nested_data.get("rows")
            columnar_rows = self._rows_from_columnar_payload(nested_columns, nested_rows)
            if columnar_rows:
                return columnar_rows
            if isinstance(nested_rows, list) and nested_rows and isinstance(nested_rows[0], dict):
                return nested_rows

        # Try common top-level fields (rows are already dicts)
        for field_name in (
            "rows",
            "data",
            "results",
            "records",
            "items",
            "entries",
            "issues",
            "values",
        ):
            if field_name in response:
                value = response[field_name]
                if isinstance(value, list):
                    return value

        # Honor configured data_field for non-SQL API endpoints.
        data_field = self.api_config.pagination.data_field
        value = self._get_nested_value(response, data_field)
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
            resp = requests.get(url, headers=headers, params=dict(params), timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = self._extract_response_rows(body, pg)
            all_rows.extend(data)

            # Check if there are more pages
            has_more = self._response_has_more(body, data, pg)
            if not has_more or not data:
                break

            cursor_value = self._extract_cursor_value(body, data, pg)
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
            params[pg.offset_param] = str(offset)
            resp = requests.get(url, headers=headers, params=dict(params), timeout=30)
            resp.raise_for_status()
            body = resp.json()

            data = self._extract_response_rows(body, pg)
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
            spec_url=self.api_config.spec_url or None,
        )

        existing_endpoints = list(self.api_config.endpoints)
        discovered_endpoints = [
            APIEndpointConfig(
                name=ep.name,
                path=ep.path,
                description=getattr(ep, "description", ""),
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

        if discovered_endpoints:
            self.api_config.endpoints = self._merge_discovered_endpoints(
                existing_endpoints,
                discovered_endpoints,
            )
        elif existing_endpoints:
            self.api_config.endpoints = existing_endpoints

        # Update pagination if discovered
        if result.pagination.type != "none":
            self.api_config.pagination = APIPaginationConfig(
                type=result.pagination.type,
                cursor_param=result.pagination.cursor_param or "starting_after",
                cursor_field=result.pagination.cursor_field or "data[-1].id",
                offset_param=result.pagination.offset_param or "offset",
                page_size_param=result.pagination.page_size_param or "limit",
                page_size=result.pagination.page_size,
                data_field=result.pagination.data_field or "data",
            )

        # Store API title and description
        if result.api_title:
            self.api_config.api_title = result.api_title
        if result.api_description:
            self.api_config.api_description = result.api_description
        if result.spec_url:
            self.api_config.spec_url = result.spec_url
        if result.base_url:
            self.api_config.base_url = result.base_url

        visible_endpoints = self.api_config.endpoints or discovered_endpoints
        return {
            "strategy": result.strategy,
            "spec_url": result.spec_url,
            "base_url": result.base_url,
            "api_title": result.api_title,
            "api_description": result.api_description,
            "endpoints_found": len(visible_endpoints),
            "endpoints": [
                {
                    "name": ep.name,
                    "path": ep.path,
                    "fields": len(getattr(ep, "fields", []) or []),
                }
                for ep in visible_endpoints
            ],
            "pagination": {
                "type": result.pagination.type,
                "data_field": result.pagination.data_field,
            },
            "errors": result.errors,
        }

    @staticmethod
    def _merge_discovered_endpoints(
        existing: list[APIEndpointConfig],
        discovered: list[APIEndpointConfig],
    ) -> list[APIEndpointConfig]:
        merged: list[APIEndpointConfig] = list(existing)
        index_by_identity = {
            (endpoint.name, endpoint.path, endpoint.method.upper()): idx
            for idx, endpoint in enumerate(merged)
        }

        for endpoint in discovered:
            identity = (endpoint.name, endpoint.path, endpoint.method.upper())
            existing_idx = index_by_identity.get(identity)
            if existing_idx is not None:
                merged[existing_idx] = endpoint
                continue
            index_by_identity[identity] = len(merged)
            merged.append(endpoint)

        return merged

    def save_connector_yaml(self, yaml_path: str | Path) -> None:
        """Save current api_config to a connector.yaml file.

        Args:
            yaml_path: Path to write the connector.yaml file.
        """
        data: dict[str, Any] = {
            "spec_version": CONNECTOR_SPEC_VERSION,
            "type": "api",
            "profile": self.api_config.profile or "api_openapi",
            "base_url": self.api_config.base_url,
        }
        if self.api_config.spec_url:
            data["spec_url"] = self.api_config.spec_url
        if self.api_config.template_id:
            data["template_id"] = self.api_config.template_id
        if self.api_config.capabilities:
            data["capabilities"] = self.api_config.capabilities

        # Add optional API metadata
        if self.api_config.api_title:
            data["api_title"] = self.api_config.api_title
        if self.api_config.api_description:
            data["api_description"] = self.api_config.api_description

        auth_data: dict[str, Any] = {
            "type": self.api_config.auth.type,
        }
        if self.api_config.auth.type in {"bearer", "header", "query_param"}:
            auth_data.update(
                {
                    "token_env": self.api_config.auth.token_env,
                    "header_name": self.api_config.auth.header_name,
                    "param_name": self.api_config.auth.param_name,
                }
            )
        if self.api_config.auth.type == "basic":
            username = self.api_config.auth.username
            password = self.api_config.auth.password
            auth_data.update(
                {
                    "username_env": self.api_config.auth.username_env,
                    "password_env": self.api_config.auth.password_env,
                    **({"username": username} if username else {}),
                    **({"password": password} if password else {}),
                }
            )
        if self.api_config.auth.type in {"jwt_login", "login"}:
            auth_data.update(
                {
                    "login_endpoint": self.api_config.auth.login_endpoint,
                    "username_env": self.api_config.auth.username_env,
                    "password_env": self.api_config.auth.password_env,
                    "token_field": self.api_config.auth.token_field,
                    "header_name": self.api_config.auth.header_name,
                    "token_prefix": self.api_config.auth.token_prefix,
                }
            )

        data.update(
            {
                "auth": auth_data,
                "endpoints": [
                    {
                        "name": ep.name,
                        "path": ep.path,
                        **({"description": ep.description} if ep.description else {}),
                        "method": ep.method,
                        "body_mode": ep.body_mode,
                        "response_mode": ep.response_mode,
                        **({"body_template": ep.body_template} if ep.body_template else {}),
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
                    "offset_param": self.api_config.pagination.offset_param,
                    "page_size_param": self.api_config.pagination.page_size_param,
                    "page_size": self.api_config.pagination.page_size,
                    "data_field": self.api_config.pagination.data_field,
                },
                "rate_limit": {
                    "requests_per_second": self.api_config.rate_limit_rps,
                },
            }
        )

        data = normalize_connector_payload(data)

        if self.api_config.capabilities:
            data["capabilities"] = self.api_config.capabilities

        path = Path(yaml_path)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
