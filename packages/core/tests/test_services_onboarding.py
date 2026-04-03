import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from db_mcp_knowledge.onboarding.schema_store import load_schema_descriptions
from db_mcp_knowledge.onboarding.state import create_initial_state, load_state
from db_mcp_models import OnboardingPhase

from db_mcp.services.onboarding import discover_structure


def test_discover_structure_filters_catalogs_and_schemas_and_saves_state():
    from db_mcp_data.connectors.sql import SQLConnector

    provider_id = "wifimetrics-trino"
    connection_path = Path("/tmp/connections/wifimetrics-trino")

    connector = MagicMock(spec=SQLConnector)
    connector.get_catalogs.return_value = ["system", "analytics"]
    connector.get_schemas.side_effect = [["information_schema", "public"]]
    # gateway.introspect() resolves the connector from connection_path

    state = create_initial_state(provider_id)
    state.phase = OnboardingPhase.INIT
    state.dialect_detected = "trino"

    ignore = MagicMock()
    ignore.patterns = ["system", "information_schema"]
    ignore.filter_catalogs.return_value = ["analytics"]
    ignore.filter_schemas.return_value = ["public"]

    with (
        patch("db_mcp.services.onboarding.load_state", return_value=state),
        patch("db_mcp.services.onboarding.load_ignore_patterns", return_value=ignore),
        patch("db_mcp.services.onboarding.save_state", return_value={"saved": True}) as mock_save,
        patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector),
    ):
        result = discover_structure(
            provider_id=provider_id,
            connection_path=connection_path,
        )

    assert result["discovered"] is True
    assert result["discovery_phase"] == "structure"
    assert result["catalogs"] == ["analytics"]
    assert result["schemas_found"] == 1
    assert result["schemas"] == [
        {"catalog": "analytics", "schema": "public", "full_name": "analytics.public"}
    ]
    assert state.catalogs_discovered == ["analytics"]
    assert state.schemas_discovered == ["public"]
    assert mock_save.call_args.kwargs["connection_path"] == connection_path


@pytest.mark.asyncio
async def test_discover_tables_background_updates_task_and_saves_with_connection_path():
    provider_id = "wifimetrics-trino"
    connection_path = Path("/tmp/connections/wifimetrics-trino")

    from db_mcp.services.onboarding import discover_tables_background

    state = create_initial_state(provider_id)
    state.phase = OnboardingPhase.INIT
    state.dialect_detected = "trino"
    state.catalogs_discovered = []

    from db_mcp_data.connectors.sql import SQLConnector

    connector = MagicMock(spec=SQLConnector)
    connector.get_schemas.return_value = [None]
    connector.get_tables.return_value = [{"name": "events", "full_name": "events"}]
    connector.get_columns.return_value = []

    ignore = MagicMock()
    ignore.filter_schemas.side_effect = lambda schemas: schemas
    ignore.filter_tables.side_effect = lambda tables: tables

    task = {"status": "running"}

    with (
        patch("db_mcp.services.onboarding.load_state", return_value=state) as mock_load_state,
        patch("db_mcp.services.onboarding.load_ignore_patterns", return_value=ignore),
        patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector),
        patch(
            "db_mcp.services.onboarding.save_schema_descriptions",
            return_value={"saved": True, "file_path": "/tmp/schema/descriptions.yaml"},
        ) as mock_save_schema,
        patch(
            "db_mcp.services.onboarding.save_state",
            return_value={"saved": True},
        ) as mock_save_state,
        patch("db_mcp.services.onboarding.get_insider_supervisor", return_value=None),
    ):
        await discover_tables_background(
            discovery_id="test-discovery",
            provider_id=provider_id,
            task=task,
            connection_path=connection_path,
        )

    assert mock_load_state.call_args.kwargs["connection_path"] == connection_path
    assert mock_save_schema.call_args.kwargs["connection_path"] == connection_path
    assert mock_save_state.call_args.kwargs["connection_path"] == connection_path
    assert task["status"] == "complete"
    assert task["result"]["tables_found"] == 1


def test_get_discovery_status_reports_running_progress():
    from db_mcp.services.onboarding import get_discovery_status

    tasks = {
        "disc-123": {
            "status": "running",
            "schemas_processed": 2,
            "schemas_total": 5,
            "tables_found_so_far": 11,
        }
    }

    result = get_discovery_status(
        discovery_id="disc-123",
        connection="analytics",
        tasks=tasks,
    )

    assert result == {
        "status": "running",
        "discovery_id": "disc-123",
        "progress_percent": 40,
        "schemas_processed": 2,
        "schemas_total": 5,
        "tables_found_so_far": 11,
        "message": "Discovery in progress: 2/5 schemas scanned, 11 tables found so far.",
        "poll_interval_seconds": 10,
        "guidance": {
            "next_steps": [
                (
                    "Poll again in 10 seconds: "
                    "mcp_setup_discover_status('disc-123', connection='analytics')"
                ),
                "Tell the user discovery is still running",
            ],
        },
    }


def test_persist_discovery_saves_schema_and_advances_state(monkeypatch):
    from db_mcp.services.onboarding import persist_discovery

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        connections_dir = Path(tmpdir) / ".db-mcp" / "connections"
        conn_path = connections_dir / "playground-copy"
        conn_path.mkdir(parents=True)

        result = persist_discovery(
            name="playground-copy",
            dialect="sqlite",
            tables=[
                {
                    "name": "Album",
                    "schema": "main",
                    "catalog": None,
                    "full_name": "main.Album",
                    "columns": [
                        {"name": "AlbumId", "type": "INTEGER"},
                        {"name": "Title", "type": "VARCHAR"},
                    ],
                },
                {
                    "name": "Artist",
                    "schema": "main",
                    "catalog": None,
                    "full_name": "main.Artist",
                    "columns": [{"name": "ArtistId", "type": "INTEGER"}],
                },
            ],
            connections_dir=connections_dir,
        )

        assert result == {
            "success": True,
            "tableCount": 2,
            "schemaCount": 1,
            "catalogCount": 0,
            "phase": "domain",
        }

        schema = load_schema_descriptions("playground-copy", connection_path=conn_path)
        assert schema is not None
        assert schema.provider_id == "playground-copy"
        assert schema.dialect == "sqlite"
        assert [table.full_name for table in schema.tables] == ["main.Album", "main.Artist"]

        state = load_state(connection_path=conn_path)
        assert state is not None
        assert state.phase == OnboardingPhase.DOMAIN
        assert state.connection_verified is True
        assert state.dialect_detected == "sqlite"
        assert state.schemas_discovered == ["main"]
        assert state.tables_discovered == ["main.Album", "main.Artist"]
        assert state.tables_total == 2


def test_complete_onboarding_marks_connection_complete(monkeypatch):
    from db_mcp.services.onboarding import complete_onboarding, persist_discovery

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        connections_dir = Path(tmpdir) / ".db-mcp" / "connections"
        conn_path = connections_dir / "playground-copy"
        conn_path.mkdir(parents=True)

        persist_discovery(
            name="playground-copy",
            dialect="sqlite",
            tables=[
                {
                    "name": "Album",
                    "schema": "main",
                    "catalog": None,
                    "full_name": "main.Album",
                    "columns": [{"name": "AlbumId", "type": "INTEGER"}],
                }
            ],
            connections_dir=connections_dir,
        )

        result = complete_onboarding(
            name="playground-copy",
            connections_dir=connections_dir,
        )

        assert result == {
            "success": True,
            "phase": "complete",
        }

        state = load_state(connection_path=conn_path)
        assert state is not None
        assert state.phase == OnboardingPhase.COMPLETE
        assert state.tables_discovered == ["main.Album"]
        assert state.tables_total == 1
