"""Superset plugin runtime."""

from __future__ import annotations

from typing import Any

from db_mcp_data.connectors.api import APIConnectorConfig, build_api_connector_config
from db_mcp_data.connectors.api_sql import APICatalogRoute, CatalogRoutingAPIConnector


class SupersetPluginConnector(CatalogRoutingAPIConnector):
    """Superset runtime for SQL-over-API routing across discovered databases."""

    def __init__(
        self,
        api_config: APIConnectorConfig,
        data_dir: str,
        env_path: str | None = None,
    ) -> None:
        super().__init__(api_config, data_dir=data_dir, env_path=env_path)
        self._schemas_by_catalog: dict[str, list[str | None]] = {}
        self._tables_by_catalog: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        self._columns_by_catalog: dict[tuple[str, str | None, str], list[dict[str, Any]]] = {}

    @classmethod
    def _extract_catalog_strings(cls, payload: Any) -> list[str]:
        values: list[str] = []
        for item in cls._extract_list_payload(payload):
            if isinstance(item, str) and item:
                values.append(item)
            elif isinstance(item, dict):
                raw = (
                    item.get("value")
                    or item.get("name")
                    or item.get("catalog")
                    or item.get("schema")
                )
                if raw:
                    values.append(str(raw))
        return values

    def _get_catalog_routes(self) -> list[APICatalogRoute]:
        if self._catalog_routes_cache is not None:
            return self._catalog_routes_cache

        headers = self._resolve_auth_headers()
        base_url = self.api_config.base_url.rstrip("/")

        db_resp = self._requests().get(f"{base_url}/api/v1/database/", headers=headers, timeout=30)
        db_resp.raise_for_status()
        databases = [
            item for item in self._extract_list_payload(db_resp.json()) if isinstance(item, dict)
        ]

        routes: list[APICatalogRoute] = []
        seen_aliases: set[str] = set()

        for item in databases:
            database_id = self._coerce_int(item.get("id"))
            if database_id is None:
                continue

            display_name = str(
                item.get("database_name")
                or item.get("name")
                or item.get("database")
                or f"database_{database_id}"
            )
            db_alias = self._identifier_alias(display_name, f"database_{database_id}")

            sql_catalogs: list[str] = []
            if item.get("allow_multi_catalog"):
                catalogs_url = f"{base_url}/api/v1/database/{database_id}/catalogs/"
                try:
                    catalogs_resp = self._requests().get(
                        catalogs_url,
                        headers=headers,
                        timeout=30,
                    )
                    catalogs_resp.raise_for_status()
                    sql_catalogs = self._extract_catalog_strings(catalogs_resp.json())
                except self._requests().exceptions.HTTPError as exc:
                    if exc.response is None or exc.response.status_code != 404:
                        raise

            if sql_catalogs:
                catalog_seen: set[str] = set()
                for sql_catalog in sql_catalogs:
                    catalog_alias = self._identifier_alias(sql_catalog, f"catalog_{database_id}")
                    if catalog_alias in catalog_seen:
                        catalog_alias = f"{catalog_alias}__{database_id}"
                    catalog_seen.add(catalog_alias)
                    alias = f"{db_alias}__{catalog_alias}"
                    if alias in seen_aliases:
                        alias = f"{alias}__{database_id}"
                    seen_aliases.add(alias)
                    routes.append(
                        APICatalogRoute(
                            alias=alias,
                            database_id=database_id,
                            display_name=f"{display_name}/{sql_catalog}",
                            sql_catalog=sql_catalog,
                        )
                    )
                continue

            alias = db_alias
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

    def _get_schema_names(self, route: APICatalogRoute) -> list[str | None]:
        if route.alias in self._schemas_by_catalog:
            return self._schemas_by_catalog[route.alias]

        headers = self._resolve_auth_headers()
        params: dict[str, Any] = {}
        if route.sql_catalog:
            params["catalog"] = route.sql_catalog

        url = (
            f"{self.api_config.base_url.rstrip('/')}/api/v1/database/"
            f"{route.database_id}/schemas/"
        )
        resp = self._requests().get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        schemas = sorted(self._extract_catalog_strings(resp.json())) or [None]
        self._schemas_by_catalog[route.alias] = schemas
        return schemas

    def _get_tables_for_route(
        self,
        route: APICatalogRoute,
        schema: str | None,
    ) -> list[dict[str, Any]]:
        cache_key = (route.alias, schema)
        if cache_key in self._tables_by_catalog:
            return self._tables_by_catalog[cache_key]

        headers = self._resolve_auth_headers()
        params: dict[str, Any] = {}
        if schema:
            params["schema"] = schema
        if route.sql_catalog:
            params["catalog"] = route.sql_catalog

        url = f"{self.api_config.base_url.rstrip('/')}/api/v1/database/{route.database_id}/tables/"
        resp = self._requests().get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()

        rows: list[dict[str, Any]] = []
        for item in self._extract_list_payload(resp.json()):
            if isinstance(item, dict):
                name = item.get("value") or item.get("name") or item.get("table")
            else:
                name = item
            if not name:
                continue
            full_name = ".".join(part for part in (route.alias, schema, str(name)) if part)
            rows.append(
                {
                    "name": str(name),
                    "schema": schema,
                    "catalog": route.alias,
                    "type": "table",
                    "full_name": full_name,
                }
            )

        self._tables_by_catalog[cache_key] = rows
        return rows

    def _get_columns_for_route(
        self,
        route: APICatalogRoute,
        table_name: str,
        schema: str | None,
    ) -> list[dict[str, Any]]:
        cache_key = (route.alias, schema, table_name)
        if cache_key in self._columns_by_catalog:
            return self._columns_by_catalog[cache_key]

        headers = self._resolve_auth_headers()
        params: dict[str, Any] = {"table": table_name}
        if schema:
            params["schema"] = schema
        if route.sql_catalog:
            params["catalog"] = route.sql_catalog

        url = (
            f"{self.api_config.base_url.rstrip('/')}/api/v1/database/"
            f"{route.database_id}/table_metadata/"
        )
        resp = self._requests().get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        raw_columns = []
        if isinstance(payload, dict):
            raw_columns = payload.get("columns") or payload.get("result") or []

        columns = [
            {
                "name": str(column.get("name")),
                "type": self._map_schema_type(column.get("type") or column.get("base_type")),
                "nullable": True,
                "default": None,
                "primary_key": False,
                "comment": None,
            }
            for column in raw_columns
            if isinstance(column, dict) and column.get("name")
        ]
        self._columns_by_catalog[cache_key] = columns
        return columns

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        schemas = {
            schema
            for route in self._selected_routes(catalog)
            for schema in self._get_schema_names(route)
            if schema
        }
        return sorted(schemas) if schemas else [None]

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for route in self._selected_routes(catalog):
            tables.extend(self._get_tables_for_route(route, schema))
        return tables

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        routes = self._selected_routes(catalog)
        if not routes:
            return super().get_columns(table_name, schema, catalog)
        if len(routes) > 1 and catalog is None:
            raise ValueError(f"Table '{table_name}' exists in multiple catalogs; specify catalog")
        return self._get_columns_for_route(routes[0], table_name, schema)


def build_superset_connector(connector_data: dict[str, Any], conn_path):
    config = build_api_connector_config(connector_data)
    return SupersetPluginConnector(
        config,
        data_dir=str(conn_path / "data"),
        env_path=str(conn_path / ".env"),
    )
