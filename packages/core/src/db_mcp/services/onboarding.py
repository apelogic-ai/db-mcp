from pathlib import Path

from db_mcp_data.connectors import get_connector
from db_mcp_data.gateway import introspect as gateway_introspect
from db_mcp_knowledge.onboarding.ignore import load_ignore_patterns
from db_mcp_knowledge.onboarding.schema_store import (
    create_initial_schema,
    load_schema_descriptions,
    rediscover_schema,
    save_schema_descriptions,
)
from db_mcp_knowledge.onboarding.state import create_initial_state, load_state, save_state
from db_mcp_models import OnboardingPhase

from db_mcp.insider import get_insider_supervisor


def discover_structure(
    provider_id: str,
    connection_path: Path,
    *,
    load_state_fn=None,
    load_ignore_patterns_fn=None,
    save_state_fn=None,
) -> dict:
    """Discover catalogs and schemas via gateway.introspect().

    connection_path is required — the gateway resolves the connector from it.
    """
    if load_state_fn is None:
        load_state_fn = load_state
    if load_ignore_patterns_fn is None:
        load_ignore_patterns_fn = load_ignore_patterns
    if save_state_fn is None:
        save_state_fn = save_state

    state = load_state_fn(provider_id, connection_path=connection_path)
    if state is None:
        return {
            "discovered": False,
            "error": "Onboarding not started. Call onboarding_start first.",
        }

    if state.phase != OnboardingPhase.INIT:
        return {
            "discovered": False,
            "error": f"Already discovered (phase: {state.phase.value}). "
            "Use onboarding_start with force=True to rediscover.",
            "phase": state.phase.value,
        }

    ignore = load_ignore_patterns_fn(provider_id, connection_path=connection_path)

    try:
        catalogs = gateway_introspect(
            provider_id, "catalogs", connection_path=connection_path
        ).get("catalogs", [])
        catalogs = ignore.filter_catalogs(catalogs)
        state.catalogs_discovered = [catalog for catalog in catalogs if catalog is not None]
    except Exception:
        catalogs = [None]
        state.catalogs_discovered = []

    all_schemas = []
    all_schemas_with_catalog = []
    try:
        for catalog in catalogs:
            schemas_raw = gateway_introspect(
                provider_id, "schemas", catalog=catalog, connection_path=connection_path
            )
            schemas = schemas_raw.get("schemas", [])
            schemas = ignore.filter_schemas(schemas)
            for schema in schemas:
                if schema is not None:
                    all_schemas.append(schema)
                    all_schemas_with_catalog.append(
                        {
                            "catalog": catalog,
                            "schema": schema,
                            "full_name": f"{catalog}.{schema}" if catalog else schema,
                        }
                    )
                else:
                    all_schemas_with_catalog.append(
                        {
                            "catalog": catalog,
                            "schema": None,
                            "full_name": "(default)",
                        }
                    )
        state.schemas_discovered = (
            all_schemas if all_schemas else (["(default)"] if all_schemas_with_catalog else [])
        )
    except Exception:
        state.schemas_discovered = []
        all_schemas_with_catalog = []

    save_result = save_state_fn(state, connection_path=connection_path)
    if not save_result["saved"]:
        return {
            "discovered": False,
            "provider_id": provider_id,
            "error": f"Failed to save state: {save_result['error']}",
        }

    return {
        "discovered": True,
        "discovery_phase": "structure",
        "provider_id": provider_id,
        "dialect": state.dialect_detected,
        "catalogs_found": len(state.catalogs_discovered),
        "catalogs": state.catalogs_discovered,
        "schemas_found": len(state.schemas_discovered),
        "schemas": all_schemas_with_catalog,
        "phase": state.phase.value,
        "next_action": "Review schemas, add ignore patterns if needed, "
        "then call onboarding_discover(phase='tables')",
    }


async def discover_tables_background(
    discovery_id: str,
    provider_id: str,
    task: dict,
    connection_path: str | Path | None = None,
    *,
    load_state_fn=None,
    load_ignore_patterns_fn=None,
    get_connector_fn=None,
    create_initial_schema_fn=None,
    save_schema_descriptions_fn=None,
    save_state_fn=None,
    get_insider_supervisor_fn=None,
) -> None:
    conn_path = Path(connection_path) if isinstance(connection_path, str) else connection_path
    # Capture before defaults so we know if caller explicitly provided a connector.
    _use_gateway = get_connector_fn is None
    if load_state_fn is None:
        load_state_fn = load_state
    if load_ignore_patterns_fn is None:
        load_ignore_patterns_fn = load_ignore_patterns
    if get_connector_fn is None:
        get_connector_fn = get_connector  # kept for backward-compat usage if needed
    if create_initial_schema_fn is None:
        create_initial_schema_fn = create_initial_schema
    if save_schema_descriptions_fn is None:
        save_schema_descriptions_fn = save_schema_descriptions
    if save_state_fn is None:
        save_state_fn = save_state
    if get_insider_supervisor_fn is None:
        get_insider_supervisor_fn = get_insider_supervisor

    try:
        state = load_state_fn(provider_id, connection_path=conn_path)
        if state is None:
            task["status"] = "error"
            task["error"] = "Onboarding state not found"
            return

        ignore = load_ignore_patterns_fn(provider_id, connection_path=conn_path)

        # Resolve connector: prefer injected fn (backward compat) or use gateway.
        if not _use_gateway:
            connector = get_connector_fn(connection_path=conn_path)

        all_schemas_filtered = []
        catalogs = state.catalogs_discovered if state.catalogs_discovered else [None]
        for catalog in catalogs:
            if _use_gateway:
                schemas_raw = gateway_introspect(
                    provider_id, "schemas", connection_path=conn_path, catalog=catalog
                )
                schemas = schemas_raw.get("schemas", [])
            else:
                schemas = connector.get_schemas(catalog=catalog)
            schemas = ignore.filter_schemas(schemas)
            for schema in schemas:
                all_schemas_filtered.append({"catalog": catalog, "schema": schema})

        state.schemas_discovered = [s["schema"] or "(default)" for s in all_schemas_filtered]
        task["schemas_total"] = len(all_schemas_filtered)

        all_tables = []
        for schema_idx, schema_info in enumerate(all_schemas_filtered):
            catalog = schema_info["catalog"]
            schema = schema_info["schema"]
            task["schemas_processed"] = schema_idx
            task["tables_found_so_far"] = len(all_tables)

            if _use_gateway:
                tables_raw = gateway_introspect(
                    provider_id, "tables", connection_path=conn_path,
                    schema=schema, catalog=catalog
                )
                tables = ignore.filter_tables(tables_raw.get("tables", []))
            else:
                tables = ignore.filter_tables(connector.get_tables(schema=schema, catalog=catalog))
            for table in tables:
                try:
                    if _use_gateway:
                        cols_raw = gateway_introspect(
                            provider_id, "columns", connection_path=conn_path,
                            table=table["name"], schema=schema, catalog=catalog
                        )
                        columns = cols_raw.get("columns", [])
                    else:
                        columns = connector.get_columns(
                            table["name"], schema=schema, catalog=catalog
                        )
                except Exception:
                    columns = []
                all_tables.append(
                    {
                        "name": table["name"],
                        "schema": schema,
                        "catalog": catalog,
                        "full_name": table["full_name"],
                        "columns": columns,
                    }
                )

        state.tables_discovered = [table["full_name"] for table in all_tables]
        state.tables_total = len(all_tables)
        task["schemas_processed"] = len(all_schemas_filtered)
        task["tables_found_so_far"] = len(all_tables)

        schema = create_initial_schema_fn(
            provider_id=provider_id,
            dialect=state.dialect_detected,
            tables=all_tables,
        )
        schema_result = save_schema_descriptions_fn(schema, connection_path=conn_path)
        if not schema_result["saved"]:
            task["status"] = "error"
            task["error"] = f"Failed to save schema descriptions: {schema_result['error']}"
            return

        state.phase = OnboardingPhase.SCHEMA
        save_result = save_state_fn(state, connection_path=conn_path)
        if not save_result["saved"]:
            task["status"] = "error"
            task["error"] = f"Failed to save state: {save_result['error']}"
            return

        supervisor = get_insider_supervisor_fn()
        if supervisor is not None:
            await supervisor.emit_new_connection(
                provider_id,
                payload={
                    "source": "onboarding_discover",
                    "discovery_id": discovery_id,
                    "tables_found": state.tables_total,
                },
            )

        task["status"] = "complete"
        task["result"] = {
            "discovered": True,
            "discovery_phase": "tables",
            "provider_id": provider_id,
            "dialect": state.dialect_detected,
            "catalogs_found": len(state.catalogs_discovered) if state.catalogs_discovered else 0,
            "schemas_found": len(state.schemas_discovered),
            "tables_found": state.tables_total,
            "phase": state.phase.value,
            "schema_file": schema_result["file_path"],
            "next_action": state.next_action(),
            "guidance": {
                "summary": (
                    f"Discovered {state.tables_total} tables "
                    f"across {len(state.schemas_discovered)} schemas"
                    + (
                        f" in {len(state.catalogs_discovered)} catalogs"
                        if state.catalogs_discovered
                        else ""
                    )
                    + "."
                ),
                "next_steps": [
                    "Describe tables one by one with onboarding_next",
                    "Or bulk-approve all tables with onboarding_bulk_approve",
                ],
            },
        }
    except Exception as error:
        task["status"] = "error"
        task["error"] = str(error)


def get_discovery_status(discovery_id: str, connection: str, tasks: dict[str, dict]) -> dict:
    task = tasks.get(discovery_id)
    if task is None:
        return {
            "status": "not_found",
            "discovery_id": discovery_id,
            "message": "Discovery task not found. It may have expired or the ID is invalid.",
        }

    status = task["status"]
    if status == "running":
        schemas_processed = task.get("schemas_processed", 0)
        schemas_total = task.get("schemas_total", 0)
        tables_found = task.get("tables_found_so_far", 0)
        progress_pct = round(100 * schemas_processed / schemas_total) if schemas_total > 0 else 0
        return {
            "status": "running",
            "discovery_id": discovery_id,
            "progress_percent": progress_pct,
            "schemas_processed": schemas_processed,
            "schemas_total": schemas_total,
            "tables_found_so_far": tables_found,
            "message": (
                f"Discovery in progress: {schemas_processed}/{schemas_total} schemas scanned, "
                f"{tables_found} tables found so far."
            ),
            "poll_interval_seconds": 10,
            "guidance": {
                "next_steps": [
                    (
                        "Poll again in 10 seconds: "
                        f"mcp_setup_discover_status('{discovery_id}', connection='{connection}')"
                    ),
                    "Tell the user discovery is still running",
                ]
            },
        }

    if status == "complete":
        return task.get("result", {})

    if status == "error":
        return {
            "status": "error",
            "discovery_id": discovery_id,
            "discovered": False,
            "error": task.get("error", "Unknown error"),
        }

    return {
        "status": "unknown",
        "discovery_id": discovery_id,
    }


def persist_discovery(
    name: str,
    tables: list[dict],
    dialect: str | None = None,
    connections_dir: Path | None = None,
) -> dict:
    if not isinstance(tables, list):
        return {"success": False, "error": "Discovered tables are required"}

    resolved_connections_dir = connections_dir or (Path.home() / ".db-mcp" / "connections")
    conn_path = resolved_connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    existing_schema = load_schema_descriptions(name, connection_path=conn_path)
    if existing_schema is not None:
        schema = rediscover_schema(existing_schema, tables)["schema"]
        if dialect:
            schema.dialect = dialect
    else:
        schema = create_initial_schema(name, dialect, tables)

    schema_result = save_schema_descriptions(schema, connection_path=conn_path)
    if not schema_result.get("saved"):
        return {
            "success": False,
            "error": schema_result.get("error") or "Failed to save schema descriptions",
        }

    state = load_state(connection_path=conn_path) or create_initial_state(name)
    state.provider_id = name
    state.phase = OnboardingPhase.DOMAIN
    state.database_url_configured = True
    state.connection_verified = True
    state.dialect_detected = dialect or state.dialect_detected

    catalogs_discovered = sorted(
        {
            str(table.get("catalog")).strip()
            for table in tables
            if table.get("catalog") not in (None, "", "null", "undefined")
        }
    )
    schemas_discovered = sorted(
        {
            str(table.get("schema") or "default").strip()
            for table in tables
            if str(table.get("schema") or "default").strip()
        }
    )
    tables_discovered = [
        str(table.get("full_name") or table.get("name") or "").strip()
        for table in tables
        if str(table.get("full_name") or table.get("name") or "").strip()
    ]

    state.catalogs_discovered = catalogs_discovered
    state.schemas_discovered = schemas_discovered
    state.tables_discovered = tables_discovered
    state.tables_total = len(tables_discovered)
    if tables_discovered:
        state.current_table = tables_discovered[0]

    state_result = save_state(state, connection_path=conn_path)
    if not state_result.get("saved"):
        return {
            "success": False,
            "error": state_result.get("error") or "Failed to save onboarding state",
        }

    return {
        "success": True,
        "tableCount": len(tables_discovered),
        "schemaCount": len(schemas_discovered),
        "catalogCount": len(catalogs_discovered),
        "phase": state.phase.value,
    }


def complete_onboarding(name: str, connections_dir: Path | None = None) -> dict:
    resolved_connections_dir = connections_dir or (Path.home() / ".db-mcp" / "connections")
    conn_path = resolved_connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    state = load_state(connection_path=conn_path) or create_initial_state(name)
    state.provider_id = name
    state.phase = OnboardingPhase.COMPLETE
    state.database_url_configured = True
    state.connection_verified = True

    existing_schema = load_schema_descriptions(name, connection_path=conn_path)
    if existing_schema is not None:
        discovered_tables = [
            table.full_name or table.get_full_name()
            for table in existing_schema.tables
            if (table.full_name or table.get_full_name())
        ]
        state.tables_discovered = discovered_tables
        state.tables_total = len(discovered_tables)
        state.schemas_discovered = sorted(
            {table.schema_name for table in existing_schema.tables if table.schema_name}
        )
        state.catalogs_discovered = sorted(
            {
                table.catalog_name
                for table in existing_schema.tables
                if table.catalog_name not in (None, "", "null", "undefined")
            }
        )
        if existing_schema.dialect:
            state.dialect_detected = existing_schema.dialect

    state_result = save_state(state, connection_path=conn_path)
    if not state_result.get("saved"):
        return {
            "success": False,
            "error": state_result.get("error") or "Failed to save onboarding state",
        }

    return {
        "success": True,
        "phase": state.phase.value,
    }
