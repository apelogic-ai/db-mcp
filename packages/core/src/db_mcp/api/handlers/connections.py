"""Connection management handlers."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import yaml
from db_mcp_data.connectors.templates import (
    list_connector_templates,
    materialize_connector_template,
)
from db_mcp_data.contracts.connector_contracts import CONNECTOR_SPEC_VERSION
from db_mcp_knowledge.vault.paths import connector_path as _connector_path

import db_mcp.services.connection as connection_service
import db_mcp.services.onboarding as onboarding_service
from db_mcp.api.helpers import _config_file, _connections_dir
from db_mcp.services.connection import (
    build_api_template_descriptor,
    create_file_connection,
    create_sql_connection,
    delete_connection,
    set_active_connection,
    switch_active_connection,
    sync_api_connection,
    test_api_connection,
    test_database_url,
    test_file_directory,
)

logger = logging.getLogger(__name__)


async def handle_connections_list(params: dict[str, Any]) -> dict[str, Any]:
    from db_mcp_data.db.connection import detect_dialect_from_url

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

    from db_mcp_data.connectors.templates import get_connector_template, match_connector_template

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

    connector_yaml = _connector_path(conn_path)
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

    connector_yaml = _connector_path(conn_path)
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
