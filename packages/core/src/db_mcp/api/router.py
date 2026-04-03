"""REST API router — replaces BICP custom handlers.

Every handler is a standalone async function that calls service functions
directly. No BICP agent dependency. Mounted at ``/api/`` on the UI server.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from db_mcp_data.connector_templates import (
    list_connector_templates,
    materialize_connector_template,
)
from db_mcp_data.contracts.connector_contracts import CONNECTOR_SPEC_VERSION
from db_mcp_data.db.connection import detect_dialect_from_url
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import db_mcp.services.agents as agents_service
import db_mcp.services.connection as connection_service
import db_mcp.services.git as git_service
import db_mcp.services.insights as insights_service
import db_mcp.services.metrics as metrics_service
import db_mcp.services.onboarding as onboarding_service
import db_mcp.services.schema as schema_service
import db_mcp.services.traces as traces_service
import db_mcp.services.vault as vault_service
from db_mcp.services.connection import (
    build_api_template_descriptor,
    create_file_connection,
    create_sql_connection,
    delete_connection,
    get_active_connection_path,
    set_active_connection,
    switch_active_connection,
    sync_api_connection,
    test_api_connection,
    test_database_url,
    test_file_directory,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONNECTIONS_DIR = Path.home() / ".db-mcp" / "connections"
_CONFIG_FILE = Path.home() / ".db-mcp" / "config.yaml"


def _connections_dir() -> Path:
    return _CONNECTIONS_DIR


def _config_file() -> Path:
    return _CONFIG_FILE


def resolve_connection_context() -> tuple[str, Path]:
    """Resolve the active connection (name, path).

    Priority:
    1. Active connection from ``~/.db-mcp/config.yaml``
    2. Process-level env vars (``CONNECTION_NAME``)
    3. Effective settings
    """
    active = get_active_connection_path(
        config_file=_config_file(),
        connections_dir=_connections_dir(),
    )
    if active is not None:
        return active.name, active

    from db_mcp.config import get_settings

    settings = get_settings()
    return settings.get_effective_provider_id(), settings.get_effective_connection_path()


def _is_git_enabled(conn_path: Path) -> bool:
    return (conn_path / ".git").exists()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def _dispatch(method: str, params: dict[str, Any]) -> Any:
    handler = HANDLERS.get(method)
    if handler is None:
        return None  # sentinel — caller returns 404
    return await handler(params)


@router.post("/{method:path}")
async def dispatch_endpoint(method: str, request: Request) -> JSONResponse:
    """Route ``POST /api/<method>`` to the matching handler function."""
    body = await request.body()
    params: dict[str, Any] = {}
    if body:
        import json as _json

        params = _json.loads(body)

    result = await _dispatch(method, params)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown method: {method}"},
        )
    return JSONResponse(content=result)


# ===================================================================
# Handler functions — one per former BICP _handle_* method.
# Each takes ``params: dict`` and returns a JSON-serialisable dict.
# ===================================================================


# ── Connections ────────────────────────────────────────────────────


async def handle_connections_list(params: dict[str, Any]) -> dict[str, Any]:
    return connection_service.list_connections_summary(
        connections_dir=_connections_dir(),
        config_file=_config_file(),
        env_connection_name=os.environ.get("CONNECTION_NAME"),
        detect_dialect_from_url=detect_dialect_from_url,
    )


async def handle_connections_switch(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name", "")
    result = switch_active_connection(
        name,
        connections_dir=_connections_dir(),
        config_file=_config_file(),
    )
    if result.get("success"):
        logger.info("Switched active connection to: %s", name)
    return result


async def handle_connections_create(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name", "").strip()
    connector_type = params.get("connectorType", "sql")
    set_active = params.get("setActive", True)

    if not name:
        return {"success": False, "error": "Connection name is required"}
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return {
            "success": False,
            "error": "Invalid name. Use only letters, numbers, dashes, underscores.",
        }

    connections_dir = _connections_dir()
    conn_path = connections_dir / name

    if conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' already exists"}

    if connector_type == "api":
        result = connection_service.create_api_connection(
            name,
            params,
            conn_path=conn_path,
            config_file=_config_file(),
            set_active=set_active,
            set_active_connection=set_active_connection,
            materialize_connector_template=materialize_connector_template,
            connector_spec_version=CONNECTOR_SPEC_VERSION,
        )
        if result.get("success"):
            tid = str(params.get("templateId", "") or "").strip()
            if tid:
                logger.info("Created API connection from template: %s (%s)", name, tid)
            else:
                logger.info("Created API connection: %s", name)
        return result

    if connector_type == "file":
        result = create_file_connection(
            name,
            params,
            conn_path=conn_path,
            config_file=_config_file(),
            set_active=set_active,
        )
        if result.get("success"):
            logger.info("Created file connection: %s", name)
        return result

    # SQL connection
    result = create_sql_connection(
        name,
        params.get("databaseUrl", "").strip(),
        connections_dir=connections_dir,
        config_file=_config_file(),
        set_active=set_active,
    )
    if result.get("success"):
        logger.info("Created connection: %s (%s)", name, result.get("dialect"))
    return result


async def handle_connections_test(params: dict[str, Any]) -> dict[str, Any]:
    connector_type = params.get("connectorType", "sql")

    if connector_type == "api":
        if not params.get("baseUrl", "").strip():
            return {"success": False, "error": "Base URL is required"}
        return test_api_connection(params, connections_dir=_connections_dir())

    if connector_type == "file":
        directory = params.get("directory", "").strip()
        if not directory:
            return {"success": False, "error": "Directory path is required"}
        return test_file_directory(directory)

    name = params.get("name")
    database_url = params.get("databaseUrl")
    connect_args = params.get("connectArgs")
    if not isinstance(connect_args, dict):
        connect_args = None

    if name:
        return connection_service.test_named_connection(
            name, connections_dir=_connections_dir()
        )
    if database_url:
        return test_database_url(database_url, connect_args=connect_args)
    return {"success": False, "error": "Either 'name' or 'databaseUrl' is required"}


async def handle_connections_delete(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}
    result = delete_connection(
        name,
        connections_dir=_connections_dir(),
        config_file=_config_file(),
    )
    if result.get("success"):
        logger.info("Deleted connection: %s", name)
    return result


async def handle_connections_get(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}

    from db_mcp_data.connector_templates import get_connector_template, match_connector_template

    return connection_service.get_named_connection_details(
        name,
        connections_dir=_connections_dir(),
        match_connector_template=match_connector_template,
        get_connector_template=get_connector_template,
    )


async def handle_connections_update(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}

    conn_path = _connections_dir() / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    connector_yaml = conn_path / "connector.yaml"
    if connector_yaml.exists():
        with open(connector_yaml) as f:
            cdata = yaml.safe_load(f) or {}

        if cdata.get("type") == "file":
            directory = params.get("directory", "").strip()
            if not directory:
                return {"success": False, "error": "Directory path is required"}
            result = connection_service.update_file_connection(
                name, directory, conn_path=conn_path
            )
            if result.get("success"):
                logger.info("Updated file connection: %s", name)
            return result

        if cdata.get("type") == "api":
            result = connection_service.update_api_connection(
                name,
                params,
                conn_path=conn_path,
                materialize_connector_template=materialize_connector_template,
            )
            if result.get("success"):
                logger.info("Updated API connection: %s", name)
            return result

    database_url = params.get("databaseUrl")
    if not database_url:
        return {"success": False, "error": "Database URL is required"}

    result = connection_service.update_sql_connection(name, database_url, conn_path=conn_path)
    if result.get("success"):
        logger.info("Updated connection: %s", name)
    return result


async def handle_connections_templates(params: dict[str, Any]) -> dict[str, Any]:
    connector_type = params.get("connectorType")
    templates = [
        build_api_template_descriptor(template.id)
        for template in list_connector_templates()
    ]
    if connector_type:
        templates = [
            t
            for t in templates
            if t is not None and t.get("connectorType") == connector_type
        ]
    return {"success": True, "templates": [t for t in templates if t is not None]}


async def handle_connections_render_template(params: dict[str, Any]) -> dict[str, Any]:
    from db_mcp.services.connection import (
        _build_api_auth_overrides,
        _build_template_env_name_overrides,
        _normalize_api_env_entries,
    )

    template_id = str(params.get("templateId", "") or "").strip()
    if not template_id:
        return {"success": False, "error": "Template id is required"}

    env_entries = _normalize_api_env_entries(params.get("envVars"))
    connector_data = materialize_connector_template(
        template_id,
        base_url=str(params.get("baseUrl", "") or "").strip() or None,
        env_name_overrides=_build_template_env_name_overrides(env_entries),
        auth_overrides=_build_api_auth_overrides(params),
    )
    if connector_data is None:
        return {"success": False, "error": f"Unknown connector template: {template_id}"}

    content = yaml.dump(connector_data, default_flow_style=False, sort_keys=False)
    return {"success": True, "content": content}


async def handle_connections_save_discovery(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}

    tables = params.get("tables") or []
    if not isinstance(tables, list):
        return {"success": False, "error": "Discovered tables are required"}

    try:
        return onboarding_service.persist_discovery(
            name=name,
            dialect=params.get("dialect"),
            tables=tables,
            connections_dir=_connections_dir(),
        )
    except Exception as e:
        logger.exception("Failed to persist discovery for %s: %s", name, e)
        return {"success": False, "error": str(e)}


async def handle_connections_complete_onboarding(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}

    try:
        return onboarding_service.complete_onboarding(
            name=name, connections_dir=_connections_dir()
        )
    except Exception as e:
        logger.exception("Failed to complete onboarding for %s: %s", name, e)
        return {"success": False, "error": str(e)}


async def handle_connections_sync(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}
    result = sync_api_connection(
        name,
        connections_dir=_connections_dir(),
        endpoint=params.get("endpoint"),
    )
    if not result.get("success"):
        logger.exception("API sync failed: %s", result.get("error"))
    return result


async def handle_connections_discover(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Connection name is required"}

    connections_dir = _connections_dir()
    conn_path = connections_dir / name

    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    connector_yaml = conn_path / "connector.yaml"
    if not connector_yaml.exists():
        return {"success": False, "error": "No connector.yaml found"}

    try:
        from db_mcp_data.connectors import ConnectorConfig
        from db_mcp_data.connectors.api import APIConnectorConfig

        return connection_service.discover_api_connection(
            name=name,
            connections_dir=connections_dir,
            load_connector_config=ConnectorConfig.from_yaml,
            api_config_type=APIConnectorConfig,
        )
    except Exception as e:
        logger.exception("API discovery failed: %s", e)
        return {"success": False, "error": str(e)}


# ── Context / Vault ────────────────────────────────────────────────


async def handle_context_tree(params: dict[str, Any]) -> dict[str, Any]:
    connections_dir = _connections_dir()

    active_connection = None
    cfg = _config_file()
    if cfg.exists():
        with open(cfg) as f:
            config = yaml.safe_load(f) or {}
            active_connection = config.get("active_connection")

    return vault_service.list_context_tree(
        connections_dir=connections_dir,
        active_connection=active_connection,
        is_git_enabled=_is_git_enabled,
    )


async def handle_context_read(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}
    return vault_service.read_context_file(
        connection_path=_connections_dir() / str(connection),
        path=str(path),
    )


async def handle_context_write(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    content = params.get("content")

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}
    if content is None:
        return {"success": False, "error": "content is required"}

    conn_path = _connections_dir() / str(connection)

    try:
        write_result = vault_service.write_context_file(
            connection_path=conn_path, path=str(path), content=str(content)
        )
        if not write_result["success"]:
            return write_result

        git_commit = vault_service.try_git_commit(conn_path, f"Update {path}", [path])
        logger.info("Wrote file: %s/%s", connection, path)
        return {"success": True, "gitCommit": git_commit}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_create(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    content = params.get("content", "")

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}

    conn_path = _connections_dir() / str(connection)

    try:
        create_result = vault_service.create_context_file(
            connection_path=conn_path, path=str(path), content=str(content)
        )
        if not create_result["success"]:
            return create_result

        git_commit = vault_service.try_git_commit(conn_path, f"Create {path}", [path])
        logger.info("Created file: %s/%s", connection, path)
        return {"success": True, "gitCommit": git_commit}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_delete(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}

    if ".." in path or path.startswith("/"):
        return {"success": False, "error": "Invalid path"}

    conn_path = _connections_dir() / connection

    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if _is_git_enabled(conn_path):
            from db_mcp_knowledge.git_utils import git

            git.rm(conn_path, path)
            git.commit(conn_path, f"Delete {path}")
            logger.info("Git rm: %s/%s", connection, path)
            return {"success": True, "gitCommit": True}

        result = vault_service.delete_context_file(
            connection_path=conn_path, path=str(path)
        )
        if result.get("success"):
            logger.info("Trashed: %s/%s -> %s", connection, path, result.get("trashedTo"))
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_add_rule(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    rule = params.get("rule")
    gap_id = params.get("gapId")

    if not connection or not rule:
        return {"success": False, "error": "connection and rule are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        result = vault_service.add_business_rule(
            connection_path=conn_path,
            connection_name=str(connection),
            rule=str(rule),
        )
        if not result["success"]:
            return {"success": False, "error": result["error"]}
        if result.get("duplicate"):
            return {"success": True, "duplicate": True}

        rel_path = "instructions/business_rules.yaml"
        vault_service.try_git_commit(conn_path, "Add business rule", [rel_path])

        if gap_id:
            try:
                from db_mcp_knowledge.gaps.store import resolve_gap

                resolve_gap(connection, gap_id, "business_rules")
            except Exception as e:
                logger.warning("Failed to resolve gap %s: %s", gap_id, e)

        logger.info("Added business rule to %s: %s", connection, str(rule)[:60])
        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_usage(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    days = params.get("days", 7)

    if not connection:
        return {"success": False, "error": "connection is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}
    return vault_service.get_context_usage(conn_path, days=days)


# ── Git ────────────────────────────────────────────────────────────


async def handle_git_history(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    limit = params.get("limit", 50)

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}

    return git_service.get_git_history(
        _connections_dir() / connection, path, limit=limit
    )


async def handle_git_show(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    commit = params.get("commit")

    if not connection or not path or not commit:
        return {"success": False, "error": "connection, path, and commit are required"}

    return git_service.get_git_content(
        _connections_dir() / connection, path, commit
    )


async def handle_git_revert(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    commit = params.get("commit")

    if not connection or not path or not commit:
        return {"success": False, "error": "connection, path, and commit are required"}

    return git_service.revert_git_file(
        _connections_dir() / connection, path, commit
    )


# ── Traces ─────────────────────────────────────────────────────────


async def handle_traces_list(params: dict[str, Any]) -> dict[str, Any]:
    active = get_active_connection_path(
        config_file=_config_file(), connections_dir=_connections_dir()
    )
    return traces_service.list_traces(
        source=params.get("source", "live"),
        connection_path=active,
        date_str=params.get("date"),
        limit=params.get("limit"),
    )


async def handle_traces_clear(params: dict[str, Any]) -> dict[str, Any]:
    return traces_service.clear_traces()


async def handle_traces_dates(params: dict[str, Any]) -> dict[str, Any]:
    active = get_active_connection_path(
        config_file=_config_file(), connections_dir=_connections_dir()
    )
    return traces_service.get_trace_dates(connection_path=active)


# ── Insights ───────────────────────────────────────────────────────


async def handle_insights_analyze(params: dict[str, Any]) -> dict[str, Any]:
    days = params.get("days", 7)
    active = get_active_connection_path(
        config_file=_config_file(), connections_dir=_connections_dir()
    )
    analysis = insights_service.analyze_insights(connection_path=active, days=days)
    return {"success": True, "analysis": analysis}


async def handle_gaps_dismiss(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    gap_id = params.get("gapId")
    reason = params.get("reason")

    if not connection or not gap_id:
        return {"success": False, "error": "connection and gapId are required"}

    try:
        result = insights_service.dismiss_gap(connection, gap_id, reason)
        if result.get("success"):
            logger.info(
                "Dismissed gap %s in %s%s", gap_id, connection,
                f": {reason}" if reason else "",
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_insights_save_example(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    sql = params.get("sql")
    intent = params.get("intent")

    if not connection or not sql or not intent:
        return {"success": False, "error": "connection, sql, and intent are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        result = insights_service.save_example(connection=connection, sql=sql, intent=intent)
        if result.get("success"):
            file_path = result.get("file_path")
            if file_path:
                vault_service.try_git_commit(
                    conn_path, "Add training example from insights", [file_path]
                )
            return {
                "success": True,
                "example_id": result["example_id"],
                "total_examples": result["total_examples"],
            }
        return {"success": False, "error": result.get("error", "Failed to save example")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Metrics ────────────────────────────────────────────────────────


async def handle_metrics_list(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    if not connection:
        return {"success": False, "error": "connection is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}
    return {"success": True, **metrics_service.list_approved_metrics(connection)}


async def handle_metrics_add(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    data = params.get("data", {})

    if not connection:
        return {"success": False, "error": "connection is required"}
    if not data or not data.get("name"):
        return {"success": False, "error": "data with name is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.add_dimension_definition(connection=connection, data=data)
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path, f"Add dimension: {data['name']}", ["metrics/dimensions.yaml"]
                )
            return result

        result = metrics_service.add_metric_definition(connection=connection, data=data)
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Add metric: {data['name']}", ["metrics/catalog.yaml"]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_metrics_update(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    name = params.get("name")
    data = params.get("data", {})

    if not connection or not name:
        return {"success": False, "error": "connection and name are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.update_dimension_definition(
                connection=connection, name=name, data=data
            )
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path,
                    f"Update dimension: {result['name']}",
                    ["metrics/dimensions.yaml"],
                )
            return result

        result = metrics_service.update_metric_definition(
            connection=connection, name=name, data=data
        )
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Update metric: {result['name']}", ["metrics/catalog.yaml"]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_metrics_delete(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    name = params.get("name")

    if not connection or not name:
        return {"success": False, "error": "connection and name are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.delete_dimension_definition(connection, name)
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path, f"Delete dimension: {name}", ["metrics/dimensions.yaml"]
                )
            return result

        result = metrics_service.delete_metric_definition(connection, name)
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Delete metric: {name}", ["metrics/catalog.yaml"]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_metrics_candidates(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    if not connection:
        return {"success": False, "error": "connection is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        result = await metrics_service.discover_metric_candidates(connection, conn_path)
        return {"success": True, **result}
    except Exception as e:
        logger.exception("Mining failed: %s", e)
        return {"success": False, "error": str(e)}


async def handle_metrics_approve(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    data = params.get("data", {})

    if not connection:
        return {"success": False, "error": "connection is required"}
    if not data or not data.get("name"):
        return {"success": False, "error": "data with name is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.approve_dimension_candidate(
                connection=connection, data=data
            )
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path,
                    f"Add dimension: {data['name']}",
                    ["metrics/dimensions.yaml"],
                )
            return result

        result = metrics_service.approve_metric_candidate(connection=connection, data=data)
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Add metric: {data['name']}", ["metrics/catalog.yaml"]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Schema ─────────────────────────────────────────────────────────


async def handle_schema_catalogs(params: dict[str, Any]) -> dict[str, Any]:
    _, conn_path = resolve_connection_context()
    return schema_service.list_catalogs(conn_path)


async def handle_schema_schemas(params: dict[str, Any]) -> dict[str, Any]:
    catalog = params.get("catalog")
    _, conn_path = resolve_connection_context()
    return schema_service.list_schemas_with_counts(conn_path, catalog=catalog)


async def handle_schema_tables(params: dict[str, Any]) -> dict[str, Any]:
    schema = params.get("schema")
    catalog = params.get("catalog")
    if not schema:
        return {"success": False, "tables": [], "error": "schema is required"}

    provider_id, conn_path = resolve_connection_context()
    return schema_service.list_tables_with_descriptions(
        connection_path=conn_path,
        provider_id=provider_id,
        schema=schema,
        catalog=catalog,
    )


async def handle_schema_columns(params: dict[str, Any]) -> dict[str, Any]:
    table = params.get("table")
    schema = params.get("schema")
    catalog = params.get("catalog")
    if not table:
        return {"success": False, "columns": [], "error": "table is required"}

    provider_id, conn_path = resolve_connection_context()
    return schema_service.describe_table_with_descriptions(
        table_name=table,
        connection_path=conn_path,
        provider_id=provider_id,
        schema=schema,
        catalog=catalog,
    )


async def handle_schema_validate_link(params: dict[str, Any]) -> dict[str, Any]:
    link = params.get("link", "")
    _, conn_path = resolve_connection_context()
    return schema_service.validate_link(link, connection_path=conn_path)


async def handle_sample_table(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    table_name = params.get("table_name")
    schema = params.get("schema")
    catalog = params.get("catalog")
    limit = params.get("limit", 5)

    if not connection:
        return {"error": "connection is required", "rows": [], "row_count": 0, "limit": 0}
    if not table_name:
        return {"error": "table_name is required", "rows": [], "row_count": 0, "limit": 0}

    try:
        limit_value = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit_value = 5

    full_name = ".".join(part for part in [catalog, schema, table_name] if part)

    try:
        return schema_service.sample_table(
            table_name=str(table_name),
            connection_path=_connections_dir() / str(connection),
            schema=str(schema) if schema else None,
            catalog=str(catalog) if catalog else None,
            limit=limit_value,
        )
    except Exception as e:
        logger.exception("Failed to sample table %s: %s", table_name, e)
        return {
            "table_name": table_name,
            "schema": schema,
            "catalog": catalog,
            "full_name": full_name or str(table_name),
            "rows": [],
            "row_count": 0,
            "limit": limit_value,
            "error": str(e),
        }


# ── Agents ─────────────────────────────────────────────────────────


async def handle_agents_list(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.list_agents()


async def handle_agents_configure(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.configure_agent(params.get("agentId", ""))


async def handle_agents_remove(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.remove_agent(params.get("agentId", ""))


async def handle_agents_config_snippet(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.get_agent_config_snippet(params.get("agentId", ""))


async def handle_agents_config_write(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.write_agent_config(
        params.get("agentId", ""), params.get("snippet", "")
    )


# ── Playground ─────────────────────────────────────────────────────


async def handle_playground_install(params: dict[str, Any]) -> dict[str, Any]:
    from db_mcp.playground import install_playground

    return install_playground()


async def handle_playground_status(params: dict[str, Any]) -> dict[str, Any]:
    from db_mcp.playground import is_playground_installed

    return {"installed": is_playground_installed()}


# ===================================================================
# Dispatch table
# ===================================================================

HANDLERS: dict[str, Any] = {
    # Connections
    "connections/list": handle_connections_list,
    "connections/switch": handle_connections_switch,
    "connections/create": handle_connections_create,
    "connections/test": handle_connections_test,
    "connections/delete": handle_connections_delete,
    "connections/get": handle_connections_get,
    "connections/update": handle_connections_update,
    "connections/templates": handle_connections_templates,
    "connections/render-template": handle_connections_render_template,
    "connections/save-discovery": handle_connections_save_discovery,
    "connections/complete-onboarding": handle_connections_complete_onboarding,
    "connections/sync": handle_connections_sync,
    "connections/discover": handle_connections_discover,
    # Context / Vault
    "context/tree": handle_context_tree,
    "context/read": handle_context_read,
    "context/write": handle_context_write,
    "context/create": handle_context_create,
    "context/delete": handle_context_delete,
    "context/add-rule": handle_context_add_rule,
    "context/usage": handle_context_usage,
    # Git
    "context/git/history": handle_git_history,
    "context/git/show": handle_git_show,
    "context/git/revert": handle_git_revert,
    # Traces
    "traces/list": handle_traces_list,
    "traces/clear": handle_traces_clear,
    "traces/dates": handle_traces_dates,
    # Insights
    "insights/analyze": handle_insights_analyze,
    "gaps/dismiss": handle_gaps_dismiss,
    "insights/save-example": handle_insights_save_example,
    # Metrics
    "metrics/list": handle_metrics_list,
    "metrics/add": handle_metrics_add,
    "metrics/update": handle_metrics_update,
    "metrics/delete": handle_metrics_delete,
    "metrics/candidates": handle_metrics_candidates,
    "metrics/approve": handle_metrics_approve,
    # Schema
    "schema/catalogs": handle_schema_catalogs,
    "schema/schemas": handle_schema_schemas,
    "schema/tables": handle_schema_tables,
    "schema/columns": handle_schema_columns,
    "schema/validate-link": handle_schema_validate_link,
    "sample_table": handle_sample_table,
    # Agents
    "agents/list": handle_agents_list,
    "agents/configure": handle_agents_configure,
    "agents/remove": handle_agents_remove,
    "agents/config-snippet": handle_agents_config_snippet,
    "agents/config-write": handle_agents_config_write,
    # Playground
    "playground/install": handle_playground_install,
    "playground/status": handle_playground_status,
}
