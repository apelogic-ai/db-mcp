"""Metabase plugin runtime."""

from __future__ import annotations

from typing import Any

from db_mcp_data.connector_plugins.compat import normalize_connector_payload
from db_mcp_data.connectors.api import (
    APIConnectorConfig,
    APIEndpointConfig,
    build_api_connector_config,
)
from db_mcp_data.connectors.api_sql import APICatalogRoute, CatalogRoutingAPIConnector


class MetabasePluginConnector(CatalogRoutingAPIConnector):
    """Metabase runtime for SQL-over-API routing across discovered databases."""

    def __init__(
        self,
        api_config: APIConnectorConfig,
        data_dir: str,
        env_path: str | None = None,
    ) -> None:
        super().__init__(api_config, data_dir=data_dir, env_path=env_path)
        self._schema_rows_by_catalog: dict[str, list[dict[str, Any]]] = {}

    def test_connection(self) -> dict[str, Any]:
        if not self.api_config.base_url:
            return {
                "connected": False,
                "dialect": self.api_config.api_title or "duckdb",
                "error": "No base_url configured",
            }

        try:
            headers = self._resolve_auth_headers()
            params = self._resolve_auth_params()
            resp = self._requests().request(
                method="GET",
                url=self.api_config.base_url.rstrip("/") + "/api/user/current",
                headers=headers,
                params=params,
                timeout=10,
            )
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

    def _runtime_path_params(self, path: str | None = None) -> dict[str, str]:
        if path is not None and "{database_id}" not in path:
            return {}
        route = self._default_route()
        if route is None:
            return {}
        return {"database_id": str(route.database_id)}

    def _runtime_template_context(self) -> dict[str, Any]:
        route = self._default_route()
        if route is None:
            return {}
        return {"database_id": route.database_id}

    def _default_route(self) -> APICatalogRoute | None:
        routes = self._get_catalog_routes()
        if self._active_catalog_alias:
            return self._resolve_catalog_route(self._active_catalog_alias)
        if routes:
            return routes[0]
        return None

    def _build_execute_sql_request(
        self,
        endpoint: APIEndpointConfig,
        sql: str,
        template_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if endpoint.name != "execute_sql":
            return super()._build_execute_sql_request(endpoint, sql, template_context)

        database_id = self._coerce_int((template_context or {}).get("database_id"))
        if database_id is None:
            route = self._default_route()
            database_id = route.database_id if route is not None else None
        if database_id is None:
            return super()._build_execute_sql_request(endpoint, sql, template_context)

        return {}, {
            "database": database_id,
            "type": "native",
            "native": {"query": sql},
        }

    def _get_catalog_routes(self) -> list[APICatalogRoute]:
        if self._catalog_routes_cache is not None:
            return self._catalog_routes_cache

        headers = self._resolve_auth_headers()
        params = self._resolve_auth_params()
        url = self.api_config.base_url.rstrip("/") + "/api/database"
        resp = self._requests().get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        items = [item for item in self._extract_list_payload(payload) if isinstance(item, dict)]
        preferred = [
            item
            for item in items
            if not item.get("is_saved_questions") and not item.get("is_sample")
        ]
        items = (
            preferred
            or [item for item in items if not item.get("is_saved_questions")]
            or items
        )

        routes: list[APICatalogRoute] = []
        seen_aliases: set[str] = set()
        for item in items:
            database_id = self._coerce_int(item.get("id"))
            if database_id is None:
                continue
            display_name = str(item.get("name") or f"database_{database_id}")
            alias = self._identifier_alias(display_name, f"database_{database_id}")
            if alias in seen_aliases:
                alias = f"{alias}__{database_id}"
            seen_aliases.add(alias)
            routes.append(
                APICatalogRoute(
                    alias=alias,
                    database_id=database_id,
                    display_name=display_name,
                )
            )

        self._catalog_routes_cache = sorted(routes, key=lambda route: route.alias)
        return self._catalog_routes_cache

    @classmethod
    def _normalize_schema_rows(cls, payload: Any) -> list[dict[str, Any]]:
        rows = [row for row in cls._extract_list_payload(payload) if isinstance(row, dict)]
        if rows:
            return rows

        if not isinstance(payload, dict):
            return []

        tables = payload.get("tables")
        if not isinstance(tables, list):
            return []

        normalized: list[dict[str, Any]] = []
        for table in tables:
            if not isinstance(table, dict):
                continue
            fields = table.get("fields") or table.get("columns") or []
            normalized.append(
                {
                    "schema": table.get("schema"),
                    "name": table.get("name") or table.get("display_name"),
                    "fields": fields if isinstance(fields, list) else [],
                }
            )
        return normalized

    def _get_schema_rows_for_route(self, route: APICatalogRoute) -> list[dict[str, Any]]:
        if route.alias in self._schema_rows_by_catalog:
            return self._schema_rows_by_catalog[route.alias]

        headers = self._resolve_auth_headers()
        params = self._resolve_auth_params()
        base_url = self.api_config.base_url.rstrip("/")
        primary_url = f"{base_url}/api/database/{route.database_id}/schema"

        try:
            resp = self._requests().get(primary_url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            rows = self._normalize_schema_rows(resp.json())
        except self._requests().exceptions.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            fallback_url = f"{base_url}/api/database/{route.database_id}/metadata"
            resp = self._requests().get(fallback_url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            rows = self._normalize_schema_rows(resp.json())

        self._schema_rows_by_catalog[route.alias] = rows
        return rows

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        schemas = {
            row.get("schema")
            for route in self._selected_routes(catalog)
            for row in self._get_schema_rows_for_route(route)
            if row.get("schema")
        }
        return sorted(schemas) if schemas else [None]

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for route in self._selected_routes(catalog):
            for row in self._get_schema_rows_for_route(route):
                row_schema = row.get("schema")
                if schema and row_schema != schema:
                    continue
                name = row.get("name")
                if not name:
                    continue
                full_name = ".".join(part for part in (route.alias, row_schema, str(name)) if part)
                tables.append(
                    {
                        "name": name,
                        "schema": row_schema,
                        "catalog": route.alias,
                        "type": "table",
                        "full_name": full_name,
                    }
                )
        return tables

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for route in self._selected_routes(catalog):
            for row in self._get_schema_rows_for_route(route):
                if row.get("name") != table_name:
                    continue
                if schema and row.get("schema") != schema:
                    continue
                matches.append(row)

        if len(matches) > 1 and catalog is None:
            raise ValueError(f"Table '{table_name}' exists in multiple catalogs; specify catalog")

        if not matches:
            return super().get_columns(table_name, schema, catalog)

        fields = matches[0].get("fields", []) or []
        return [
            {
                "name": field.get("name"),
                "type": self._map_schema_type(field.get("base_type") or field.get("type")),
                "nullable": True,
                "default": None,
                "primary_key": False,
                "comment": None,
            }
            for field in fields
            if isinstance(field, dict) and field.get("name")
        ]


def build_metabase_connector(connector_data: dict[str, Any], conn_path):
    config = build_api_connector_config(normalize_connector_payload(connector_data))
    return MetabasePluginConnector(
        config,
        data_dir=str(conn_path / "data"),
        env_path=str(conn_path / ".env"),
    )
