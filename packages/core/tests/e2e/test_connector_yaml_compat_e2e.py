from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from db_mcp.config import Settings
from db_mcp.connector_plugins.builtin.metabase import MetabasePluginConnector
from db_mcp.connector_templates import materialize_connector_template
from db_mcp.connectors import ConnectorConfig, get_connector
from db_mcp.connectors.api import APIConnector, APIConnectorConfig
from db_mcp.registry import ConnectionRegistry


def _write_connection(
    connections_dir: Path,
    name: str,
    payload: dict,
    *,
    env: str = "",
) -> Path:
    connection_dir = connections_dir / name
    connection_dir.mkdir(parents=True, exist_ok=True)
    (connection_dir / "connector.yaml").write_text(yaml.safe_dump(payload, sort_keys=False))
    if env:
        (connection_dir / ".env").write_text(env)
    return connection_dir


def _build_legacy_metabase_payload() -> dict:
    payload = materialize_connector_template(
        "metabase",
        base_url="https://metabase.example.com",
    )
    assert payload is not None

    payload = deepcopy(payload)
    payload["spec_version"] = "1.0.0"
    payload["display_name"] = "Legacy Metabase"
    payload["generated_at"] = "2026-03-30T12:00:00Z"
    payload["ui_state"] = {"sample_table": "dashboard"}
    payload["auth"]["prompt"] = "Metabase API key"
    payload["auth"]["secret_slot"] = "metabase_api_key"
    payload["pagination"]["strategy_name"] = "legacy_none"
    payload["rate_limit"] = {"requests_per_second": 10.0, "burst": 20}

    dashboard_endpoint = next(
        endpoint for endpoint in payload["endpoints"] if endpoint["name"] == "dashboard"
    )
    dashboard_endpoint["description"] = "List all dashboards"
    dashboard_endpoint["summary"] = "Dashboards"
    dashboard_endpoint["deprecated"] = False
    dashboard_endpoint["query_params"][0]["description"] = "Dashboard filter"
    dashboard_endpoint["query_params"][0]["default"] = "all"
    dashboard_endpoint["query_params"][0]["style"] = "form"
    dashboard_endpoint["query_params"][0]["explode"] = False

    execute_sql_endpoint = next(
        endpoint for endpoint in payload["endpoints"] if endpoint["name"] == "execute_sql"
    )
    execute_sql_endpoint["description"] = "Execute native SQL"
    execute_sql_endpoint["operation_id"] = "executeSql"
    execute_sql_endpoint["deprecated"] = False
    execute_sql_endpoint["body_template"] = {
        "database": "{{database_id}}",
        "type": "native",
        "native": {"query": "{{sql}}"},
    }

    return payload


def _build_noisy_generic_api_payload() -> dict:
    return {
        "spec_version": "1.0.0",
        "type": "api",
        "profile": "api_openapi",
        "base_url": "https://api.example.com",
        "description": "Generic API",
        "unknown_flag": True,
        "legacy_hint": "safe to ignore",
        "auth": {
            "type": "header",
            "token_env": "API_KEY",
            "header_name": "Authorization",
            "display_name": "Primary token",
        },
        "endpoints": [
            {
                "name": "search",
                "path": "/search",
                "method": "POST",
                "description": "Search endpoint",
                "body_mode": "json",
                "body_template": {"query": "{{sql}}"},
                "response_mode": "raw",
                "summary": "Search",
                "query_params": [
                    {
                        "name": "limit",
                        "type": "integer",
                        "description": "Page size",
                        "default": "10",
                        "enum": ["10", "20"],
                        "style": "form",
                    }
                ],
            }
        ],
        "pagination": {
            "type": "offset",
            "offset_param": "offset",
            "page_size_param": "limit",
            "page_size": 50,
            "strategy_name": "offset_limit",
        },
        "rate_limit": {"requests_per_second": 5.0, "burst": 10},
    }


def test_runtime_loads_generic_api_connection_with_noisy_connector_yaml(tmp_path):
    conn_dir = _write_connection(
        tmp_path,
        "generic-api",
        _build_noisy_generic_api_payload(),
        env="API_KEY=test-token\n",
    )

    config = ConnectorConfig.from_yaml(conn_dir / "connector.yaml")
    assert isinstance(config, APIConnectorConfig)
    assert config.endpoints[0].description == "Search endpoint"
    assert config.endpoints[0].body_template == {"query": "{{sql}}"}
    assert config.endpoints[0].query_params[0].description == "Page size"
    assert config.endpoints[0].query_params[0].default == "10"
    assert config.pagination.page_size == 50

    connector = get_connector(str(conn_dir))
    assert isinstance(connector, APIConnector)
    assert connector.api_config.endpoints[0].description == "Search endpoint"
    assert connector.api_config.endpoints[0].body_template == {"query": "{{sql}}"}


def test_runtime_loads_legacy_metabase_connector_yaml_and_round_trips_cleanly(tmp_path):
    conn_dir = _write_connection(
        tmp_path,
        "legacy-metabase",
        _build_legacy_metabase_payload(),
        env="X_API_KEY=mb-api-key-123\n",
    )

    config = ConnectorConfig.from_yaml(conn_dir / "connector.yaml")
    assert isinstance(config, APIConnectorConfig)

    connector = get_connector(str(conn_dir))
    assert isinstance(connector, MetabasePluginConnector)

    execute_sql_endpoint = next(
        endpoint for endpoint in connector.api_config.endpoints if endpoint.name == "execute_sql"
    )
    dashboard_endpoint = next(
        endpoint for endpoint in connector.api_config.endpoints if endpoint.name == "dashboard"
    )

    assert execute_sql_endpoint.body_template is None
    assert execute_sql_endpoint.description == ""
    assert dashboard_endpoint.description == ""
    assert dashboard_endpoint.query_params[0].description == ""
    assert dashboard_endpoint.query_params[0].default is None

    connector.save_connector_yaml(conn_dir / "connector.roundtrip.yaml")
    saved = yaml.safe_load((conn_dir / "connector.roundtrip.yaml").read_text())

    saved_execute_sql_endpoint = next(
        endpoint for endpoint in saved["endpoints"] if endpoint["name"] == "execute_sql"
    )
    saved_dashboard_endpoint = next(
        endpoint for endpoint in saved["endpoints"] if endpoint["name"] == "dashboard"
    )

    assert "body_template" not in saved_execute_sql_endpoint
    assert "description" not in saved_execute_sql_endpoint
    assert "description" not in saved_dashboard_endpoint
    assert saved_dashboard_endpoint["query_params"] == [{"name": "f", "type": "string"}]


def test_registry_loads_multiple_connections_with_noisy_connector_yaml(tmp_path):
    connections_dir = tmp_path / "connections"
    _write_connection(
        connections_dir,
        "legacy-metabase",
        _build_legacy_metabase_payload(),
        env="X_API_KEY=mb-api-key-123\n",
    )
    _write_connection(
        connections_dir,
        "generic-api",
        _build_noisy_generic_api_payload(),
        env="API_KEY=test-token\n",
    )

    ConnectionRegistry.reset()
    registry = ConnectionRegistry(
        Settings(connections_dir=str(connections_dir), connection_name="legacy-metabase")
    )

    connections = registry.discover()

    assert set(connections) == {"generic-api", "legacy-metabase"}
    assert registry.get_connector("legacy-metabase").__class__ is MetabasePluginConnector
    assert isinstance(registry.get_connector("generic-api"), APIConnector)
