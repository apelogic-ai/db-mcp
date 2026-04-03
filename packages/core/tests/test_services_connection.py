"""Tests for connection resolution services."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from db_mcp_models import OnboardingPhase


def _make_connection_info(name, path="/tmp/conn", conn_type="sql", dialect="trino"):
    from db_mcp.registry import ConnectionInfo

    return ConnectionInfo(
        name=name,
        path=Path(path),
        type=conn_type,
        dialect=dialect,
        description="",
        is_default=False,
    )


def test_service_resolve_connection_named_connection_returns_connector_name_and_path():
    from db_mcp.services.connection import resolve_connection

    mock_connector = MagicMock()
    conn_info = _make_connection_info("analytics", "/tmp/analytics", "sql")

    mock_registry = MagicMock()
    mock_registry.discover.return_value = {"analytics": conn_info}
    mock_registry.get_connector.return_value = mock_connector

    with patch("db_mcp.services.connection.ConnectionRegistry") as mock_registry_cls:
        mock_registry_cls.get_instance.return_value = mock_registry
        connector, name, path = resolve_connection("analytics")

    assert connector is mock_connector
    assert name == "analytics"
    assert path == Path("/tmp/analytics")


def test_service_get_named_connection_details_prefers_connector_yaml_database_url_over_env(
    tmp_path: Path,
):
    from db_mcp.services.connection import get_named_connection_details

    conn_path = tmp_path / "top-ledger"
    conn_path.mkdir(parents=True)
    (conn_path / ".env").write_text('DATABASE_URL="trino://user@host:8443/catalog-from-env"\n')
    (conn_path / "connector.yaml").write_text(
        "type: sql\n"
        "database_url: trino://user@host:8443/catalog-from-yaml\n"
        "capabilities:\n"
        "  connect_args:\n"
        "    http_scheme: http\n"
    )

    result = get_named_connection_details(
        "top-ledger",
        connections_dir=tmp_path,
    )

    assert result["success"] is True
    assert result["connectorType"] == "sql"
    assert result["databaseUrl"] == "trino://user@host:8443/catalog-from-yaml"


def test_service_update_api_connection_from_template_rewrites_connector_and_env(tmp_path: Path):
    from db_mcp_data.connector_templates import materialize_connector_template

    from db_mcp.services.connection import update_api_connection

    conn_path = tmp_path / "lens"
    conn_path.mkdir(parents=True)
    (conn_path / "connector.yaml").write_text(
        "spec_version: 1.0.0\n"
        "type: api\n"
        "profile: api_openapi\n"
        "base_url: https://api.example.com\n"
        "auth:\n"
        "  type: none\n"
        "endpoints: []\n"
        "pagination:\n"
        "  type: none\n"
    )

    result = update_api_connection(
        "lens",
        {
            "templateId": "metabase",
            "baseUrl": "https://metabase.k8slens.dev",
            "envVars": [
                {
                    "slot": "X_API_KEY",
                    "name": "API_KEY",
                    "value": "secret-token",
                    "secret": True,
                }
            ],
        },
        conn_path=conn_path,
        materialize_connector_template=materialize_connector_template,
    )

    assert result["success"] is True
    connector_yaml = (conn_path / "connector.yaml").read_text()
    env_text = (conn_path / ".env").read_text()

    assert "template_id: metabase" in connector_yaml
    assert "profile: hybrid_bi" in connector_yaml
    assert "header_name: x-api-key" in connector_yaml
    assert "path: /api/dataset" in connector_yaml
    assert "API_KEY=secret-token" in env_text


def test_service_create_api_connection_from_template_saves_connector_and_env(tmp_path: Path):
    from db_mcp_data.connector_templates import materialize_connector_template

    from db_mcp.services.connection import create_api_connection

    conn_path = tmp_path / "lens"

    result = create_api_connection(
        "lens",
        {
            "baseUrl": "https://metabase.k8slens.dev",
            "templateId": "metabase",
            "envVars": [
                {
                    "slot": "X_API_KEY",
                    "name": "API_KEY",
                    "value": "secret-token",
                    "secret": True,
                }
            ],
        },
        conn_path=conn_path,
        set_active=False,
        materialize_connector_template=materialize_connector_template,
        connector_spec_version="1.0.0",
    )

    assert result["success"] is True
    connector_yaml = (conn_path / "connector.yaml").read_text()
    env_text = (conn_path / ".env").read_text()

    assert "profile: hybrid_bi" in connector_yaml
    assert "path: /api/dataset" in connector_yaml
    assert "token_env: API_KEY" in connector_yaml
    assert "header_name: x-api-key" in connector_yaml
    assert "API_KEY=secret-token" in env_text


def test_service_update_sql_connection_writes_database_url(tmp_path: Path):
    from db_mcp.services.connection import update_sql_connection

    conn_path = tmp_path / "warehouse"
    conn_path.mkdir(parents=True)

    result = update_sql_connection(
        "warehouse",
        "trino://user@host:8443/analytics",
        conn_path=conn_path,
    )

    assert result == {"success": True, "name": "warehouse"}
    assert (conn_path / ".env").read_text() == "DATABASE_URL=trino://user@host:8443/analytics\n"


def test_service_update_file_connection_rewrites_directory(tmp_path: Path):
    from db_mcp.services.connection import update_file_connection

    conn_path = tmp_path / "files"
    conn_path.mkdir(parents=True)
    connector_yaml = conn_path / "connector.yaml"
    connector_yaml.write_text(
        "spec_version: 1.0.0\n"
        "type: file\n"
        "profile: file_local\n"
        "directory: /old/path\n"
    )

    result = update_file_connection(
        "files",
        "/new/path",
        conn_path=conn_path,
    )

    assert result == {"success": True, "name": "files"}
    assert "directory: /new/path" in connector_yaml.read_text()


def test_service_discover_api_connection_persists_onboarding_state(tmp_path: Path):
    from db_mcp_data.connectors.api import APIConnectorConfig
    from db_mcp_knowledge.onboarding.state import load_state

    from db_mcp.services.connection import discover_api_connection

    connections_dir = tmp_path / ".db-mcp" / "connections"
    conn_path = connections_dir / "dune"
    conn_path.mkdir(parents=True)
    connector_yaml = conn_path / "connector.yaml"
    connector_yaml.write_text("type: api\nbase_url: https://api.dune.com/api/v1\nendpoints: []\n")

    fake_config = APIConnectorConfig(base_url="https://api.dune.com/api/v1")
    fake_connector = MagicMock()
    fake_connector.discover.return_value = {
        "strategy": "openapi",
        "endpoints_found": 2,
        "endpoints": [
            {"name": "execute_sql", "path": "/sql/execute", "fields": 3},
            {
                "name": "execution_status",
                "path": "/execution/{execution_id}/status",
                "fields": 2,
            },
        ],
    }

    result = discover_api_connection(
        name="dune",
        connections_dir=connections_dir,
        load_connector_config=lambda path: fake_config,
        get_runtime_connector=lambda path: fake_connector,
        api_config_type=APIConnectorConfig,
    )

    assert result["success"] is True
    assert result["endpoints_found"] == 2
    fake_connector.save_connector_yaml.assert_called_once_with(connector_yaml)

    state = load_state(connection_path=conn_path)
    assert state is not None
    assert state.phase == OnboardingPhase.DOMAIN
    assert state.connection_verified is True
    assert state.database_url_configured is True
    assert state.tables_discovered == [
        "/execution/{execution_id}/status",
        "/sql/execute",
    ]
    assert state.tables_total == 2


