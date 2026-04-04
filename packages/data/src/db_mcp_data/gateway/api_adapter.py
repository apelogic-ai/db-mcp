"""APIAdapter — drives APIConnector instances through the gateway protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from db_mcp_models.gateway import ColumnMeta, DataRequest, DataResponse, EndpointQuery, SQLQuery

from db_mcp_data.gateway.adapter import VALID_SCOPES


class APIAdapter:
    """Stateless adapter for APIConnector.

    Handles two distinct execution paths:
      - EndpointQuery  → connector.query_endpoint()   (REST/paged fetch)
      - SQLQuery       → connector.execute_sql()       (API-SQL, e.g. Dune)
        execute_sql on APIConnector already handles async polling internally.
    """

    # ------------------------------------------------------------------
    # Protocol: can_handle
    # ------------------------------------------------------------------

    def can_handle(self, connector: Any) -> bool:
        """True only for APIConnector instances."""
        from db_mcp_data.connectors.api import APIConnector

        return isinstance(connector, APIConnector)

    # ------------------------------------------------------------------
    # Protocol: execute
    # ------------------------------------------------------------------

    def execute(
        self,
        connector: Any,
        request: DataRequest,
        *,
        connection_path: Path,
    ) -> dict[str, Any]:
        """Dispatch to the appropriate execution path based on query type."""
        if isinstance(request.query, EndpointQuery):
            return self._execute_endpoint(connector, request.query)
        if isinstance(request.query, SQLQuery):
            return self._execute_sql(connector, request.query)
        return DataResponse(
            status="error", data=[], columns=[], rows_returned=0,
            error=f"APIAdapter received unsupported query type: {type(request.query).__name__}",
        )

    def _execute_endpoint(
        self, connector: Any, query: EndpointQuery
    ) -> DataResponse:
        try:
            response = connector.query_endpoint(
                query.endpoint,
                params=query.params or None,
                max_pages=query.max_pages,
                method_override=query.method if query.method != "GET" else None,
            )
        except Exception as exc:
            return DataResponse(
                status="error", data=[], columns=[], rows_returned=0, error=str(exc)
            )

        if "error" in response:
            return DataResponse(status="error", data=[], columns=[], rows_returned=0,
                                error=response["error"])

        data = response.get("data", [])
        # response_mode=raw returns a single dict or scalar; normalize to list[dict]
        if isinstance(data, dict):
            rows: list[dict] = [data]
        elif not isinstance(data, list):
            rows = [{"value": data}]
        else:
            rows = data
        columns = [ColumnMeta(name=k) for k in (rows[0].keys() if rows else [])]
        return DataResponse(status="success", data=rows, columns=columns, rows_returned=len(rows))

    def _execute_sql(self, connector: Any, query: SQLQuery) -> DataResponse:
        try:
            rows = connector.execute_sql(query.sql, query.params or None)
        except Exception as exc:
            return DataResponse(
                status="error", data=[], columns=[], rows_returned=0, error=str(exc)
            )

        columns = [ColumnMeta(name=k) for k in (rows[0].keys() if rows else [])]
        return DataResponse(status="success", data=rows, columns=columns, rows_returned=len(rows))

    # ------------------------------------------------------------------
    # Protocol: introspect
    # ------------------------------------------------------------------

    def introspect(
        self,
        connector: Any,
        scope: str,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str | None = None,
        connection_path: Path | None = None,
    ) -> dict[str, Any]:
        """Return schema objects for *scope* — delegates to connector methods."""
        if scope not in VALID_SCOPES:
            return {
                "status": "error",
                "error": (
                    f"Invalid scope '{scope}'. "
                    f"Must be one of: {sorted(VALID_SCOPES)}"
                ),
            }

        try:
            if scope == "catalogs":
                return {"catalogs": connector.get_catalogs()}

            if scope == "schemas":
                return {"schemas": connector.get_schemas(catalog=catalog)}

            if scope == "tables":
                return {"tables": connector.get_tables(schema=schema, catalog=catalog)}

            # scope == "columns"
            if table is None:
                return {
                    "status": "error",
                    "error": "'table' is required when scope='columns'",
                }
            return {"columns": connector.get_columns(table, schema=schema, catalog=catalog)}

        except Exception as exc:
            return {"status": "error", "error": str(exc)}
