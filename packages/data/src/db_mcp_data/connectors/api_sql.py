"""Generic helpers for SQL-backed API connectors with catalog routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlglot import exp, parse_one

from db_mcp_data.connectors.api import APIConnector


@dataclass
class APICatalogRoute:
    """Resolved routing context for a catalog-like SQL namespace."""

    alias: str
    database_id: int
    display_name: str
    sql_catalog: str | None = None


class CatalogRoutingAPIConnector(APIConnector):
    """Base connector for API products that route SQL through per-catalog contexts."""

    def __init__(
        self,
        api_config,
        data_dir: str,
        env_path: str | None = None,
    ) -> None:
        super().__init__(api_config, data_dir=data_dir, env_path=env_path)
        self._catalog_routes_cache: list[APICatalogRoute] | None = None
        self._active_catalog_alias: str | None = None

    @staticmethod
    def _identifier_alias(value: str | None, fallback: str) -> str:
        candidate = (value or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_]+", "_", candidate)
        candidate = re.sub(r"_+", "_", candidate).strip("_")
        if not candidate:
            candidate = fallback.lower()
        if candidate[0].isdigit():
            candidate = f"catalog_{candidate}"
        return candidate

    @classmethod
    def _extract_list_payload(cls, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("result", "data", "tables", "schemas", "catalogs"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _table_catalog_name(table: exp.Table) -> str | None:
        catalog = table.args.get("catalog")
        if catalog is None:
            return None
        if isinstance(catalog, exp.Identifier):
            return catalog.name
        raw = getattr(catalog, "this", None)
        return str(raw) if raw is not None else str(catalog)

    @classmethod
    def _extract_sql_catalog_aliases(cls, sql: str, valid_aliases: set[str]) -> set[str]:
        try:
            expression = parse_one(sql)
        except Exception:
            return {
                alias
                for alias in valid_aliases
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}\.", sql)
            }

        aliases: set[str] = set()
        for table in expression.find_all(exp.Table):
            catalog = cls._table_catalog_name(table)
            if catalog and catalog in valid_aliases:
                aliases.add(catalog)
        return aliases

    @classmethod
    def _rewrite_sql_catalog_alias(
        cls,
        sql: str,
        alias: str,
        replacement_catalog: str | None,
    ) -> str:
        try:
            expression = parse_one(sql)
        except Exception:
            replacement = f"{replacement_catalog}." if replacement_catalog else ""
            return re.sub(rf"(?<![A-Za-z0-9_]){re.escape(alias)}\.", replacement, sql)

        changed = False
        for table in expression.find_all(exp.Table):
            catalog = cls._table_catalog_name(table)
            if catalog != alias:
                continue
            changed = True
            if replacement_catalog:
                table.set("catalog", exp.to_identifier(replacement_catalog))
            else:
                table.set("catalog", None)

        return expression.sql() if changed else sql

    def _get_catalog_routes(self) -> list[APICatalogRoute]:
        raise NotImplementedError

    def _get_sql_catalog_replacement(self, route: APICatalogRoute) -> str | None:
        return route.sql_catalog

    def _build_route_template_context(self, route: APICatalogRoute) -> dict[str, Any]:
        return {
            "database_id": route.database_id,
            "sql_catalog": route.sql_catalog,
        }

    def _resolve_catalog_route(self, catalog: str) -> APICatalogRoute:
        for route in self._get_catalog_routes():
            if route.alias == catalog:
                return route
        raise ValueError(f"Unknown catalog '{catalog}'")

    def _selected_routes(self, catalog: str | None) -> list[APICatalogRoute]:
        routes = self._get_catalog_routes()
        if catalog:
            self._active_catalog_alias = catalog
            return [self._resolve_catalog_route(catalog)]
        if len(routes) == 1:
            return routes
        return routes

    def _resolve_sql_route(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[APICatalogRoute, str]:
        routes = self._get_catalog_routes()
        if not routes:
            raise ValueError("No catalogs available for SQL routing")

        explicit_catalog = None
        if isinstance(params, dict):
            raw_catalog = params.get("catalog")
            if isinstance(raw_catalog, str) and raw_catalog.strip():
                explicit_catalog = raw_catalog.strip()

        if explicit_catalog:
            route = self._resolve_catalog_route(explicit_catalog)
            self._active_catalog_alias = route.alias
        else:
            route_by_alias = {route.alias: route for route in routes}
            aliases_in_sql = self._extract_sql_catalog_aliases(sql, set(route_by_alias))
            if len(aliases_in_sql) > 1:
                raise ValueError(
                    "SQL references multiple catalogs. Select exactly one catalog per query."
                )
            if len(aliases_in_sql) == 1:
                route = route_by_alias[next(iter(aliases_in_sql))]
                self._active_catalog_alias = route.alias
            elif self._active_catalog_alias:
                route = self._resolve_catalog_route(self._active_catalog_alias)
            elif len(routes) == 1:
                route = routes[0]
            else:
                aliases = ", ".join(route.alias for route in routes)
                raise ValueError(
                    "Multiple catalogs available; qualify the query with one of: "
                    f"{aliases}"
                )

        rewritten_sql = self._rewrite_sql_catalog_alias(
            sql,
            route.alias,
            self._get_sql_catalog_replacement(route),
        )
        return route, rewritten_sql

    def get_catalogs(self) -> list[str | None]:
        routes = self._get_catalog_routes()
        if routes:
            return [route.alias for route in routes]
        return super().get_catalogs()

    def submit_sql(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        routes = self._get_catalog_routes()
        if not routes:
            return super().submit_sql(sql, params=params)

        caps = self.api_config.capabilities
        supports_sql = caps.get("supports_sql")
        if supports_sql is None:
            supports_sql = caps.get("sql")
        if not supports_sql:
            rows = super().execute_sql(sql, None)
            return {"mode": "sync", "rows": rows}

        execute_endpoint = self._get_endpoint("execute_sql")
        if execute_endpoint is None:
            raise ValueError(
                "No 'execute_sql' endpoint configured. "
                "Add an endpoint named 'execute_sql' to connector.yaml."
            )

        route, routed_sql = self._resolve_sql_route(sql, params)
        runtime_context = {
            **self._runtime_template_context(),
            **{
                key: value
                for key, value in self._build_route_template_context(route).items()
                if value is not None
            },
        }
        headers = self._resolve_auth_headers()

        runtime_params = self._runtime_path_params(execute_endpoint.path)
        rendered_path, runtime_params = self._render_path(execute_endpoint.path, runtime_params)
        url = self.api_config.base_url.rstrip("/") + rendered_path
        query_params, body = self._build_execute_sql_request(
            execute_endpoint,
            routed_sql,
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
            resp = self._requests().post(url, **request_kwargs)
            resp.raise_for_status()
            response = resp.json()
        except self._requests().exceptions.HTTPError as exc:
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
                resp = self._requests().post(url, **request_kwargs)
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

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        routes = self._get_catalog_routes()
        if not routes:
            return super().get_table_sample(table_name, schema, catalog, limit)

        source = ".".join(part for part in (catalog, schema, table_name) if part)
        params = {"catalog": catalog} if catalog else None
        return self.execute_sql(f"SELECT * FROM {source} LIMIT {limit}", params)

    @staticmethod
    def _requests():
        import db_mcp_data.connectors.api as api_module

        return api_module.requests
