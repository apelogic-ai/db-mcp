"""SQLAdapter — drives SQLConnector instances through the gateway protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from db_mcp_models.gateway import ColumnMeta, DataRequest, DataResponse, SQLQuery

from db_mcp_data.gateway.adapter import VALID_SCOPES


class SQLAdapter:
    """Stateless adapter for SQLConnector.

    Normalises execute_sql / get_* calls into the gateway's uniform dict shape.
    """

    # ------------------------------------------------------------------
    # Protocol: can_handle
    # ------------------------------------------------------------------

    def can_handle(self, connector: Any) -> bool:
        """True only for SQLConnector instances (not API or File sub-types)."""
        from db_mcp_data.connectors.api import APIConnector
        from db_mcp_data.connectors.file import FileConnector
        from db_mcp_data.connectors.sql import SQLConnector

        return (
            isinstance(connector, SQLConnector)
            and not isinstance(connector, (APIConnector, FileConnector))
        )

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
        """Execute a SQLQuery and return a normalised result dict."""
        if not isinstance(request.query, SQLQuery):
            return DataResponse(
                status="error", data=[], columns=[], rows_returned=0,
                error=(
                    f"SQLAdapter requires a SQLQuery, got "
                    f"{type(request.query).__name__}. "
                    "Use APIAdapter for EndpointQuery."
                ),
            )

        try:
            rows = connector.execute_sql(request.query.sql, request.query.params or None)
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
        """Return schema objects for *scope* from the connector."""
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
