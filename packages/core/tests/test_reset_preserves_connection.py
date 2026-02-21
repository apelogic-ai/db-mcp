"""Test that reset preserves connection state instead of deleting file."""

import tempfile
from pathlib import Path

from db_mcp_models import OnboardingPhase, OnboardingState

from db_mcp.onboarding.state import delete_state, load_state, save_state
from db_mcp.registry import ConnectionRegistry


def test_reset_preserves_connection_facts():
    """Test that delete_state preserves connection facts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn_path = Path(tmpdir)

        # Create an onboarding state with connection facts and progress
        original_state = OnboardingState(
            provider_id="test-provider",
            phase=OnboardingPhase.DOMAIN,
            database_url_configured=True,
            connection_verified=True,
            dialect_detected="postgresql",
            catalogs_discovered=["catalog1", "catalog2"],
            schemas_discovered=["public", "schema1"],
            tables_discovered=["table1", "table2", "table3"],
            tables_total=5,
            current_table="table2",
            domain_model_generated=True,
            domain_model_approved=False,
            entities_total=3,
            entities_interviewed=2,
            rules_captured=10,
            examples_added=5,
        )

        # Save the original state
        save_result = save_state(original_state, connection_path=conn_path)
        assert save_result["saved"] is True

        # Reset the state
        delete_result = delete_state(connection_path=conn_path)
        assert delete_result["deleted"] is True
        assert delete_result["error"] is None

        # Verify state file still exists
        state_file = conn_path / "state.yaml"
        assert state_file.exists()

        # Load the reset state
        reset_state = load_state(connection_path=conn_path)
        assert reset_state is not None

        # Verify connection facts are preserved
        assert reset_state.provider_id == "test-provider"
        assert reset_state.database_url_configured is True
        assert reset_state.connection_verified is True
        assert reset_state.dialect_detected == "postgresql"
        assert reset_state.catalogs_discovered == ["catalog1", "catalog2"]
        assert reset_state.schemas_discovered == ["public", "schema1"]
        assert reset_state.tables_discovered == ["table1", "table2", "table3"]

        # Verify progress is reset
        assert reset_state.phase == OnboardingPhase.INIT
        assert reset_state.tables_total == 0
        assert reset_state.current_table is None
        assert reset_state.domain_model_generated is False
        assert reset_state.domain_model_approved is False
        assert reset_state.pending_domain_model is None
        assert reset_state.entities_total == 0
        assert reset_state.entities_interviewed == 0
        assert reset_state.rules_captured == 0
        assert reset_state.current_entity is None
        assert reset_state.pending_rules == []
        assert reset_state.examples_added == 0


def test_reset_handles_missing_state():
    """Test that reset handles missing state file gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn_path = Path(tmpdir)

        # Try to reset non-existent state
        delete_result = delete_state(connection_path=conn_path)
        assert delete_result["deleted"] is False
        assert delete_result["error"] == "State file not found"


def test_reset_with_minimal_existing_state():
    """Test reset with minimal existing state (just provider_id)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn_path = Path(tmpdir)

        # Create minimal state
        minimal_state = OnboardingState(
            provider_id="minimal-provider",
            phase=OnboardingPhase.COMPLETE,
        )

        save_result = save_state(minimal_state, connection_path=conn_path)
        assert save_result["saved"] is True

        # Reset the state
        delete_result = delete_state(connection_path=conn_path)
        assert delete_result["deleted"] is True

        # Load reset state
        reset_state = load_state(connection_path=conn_path)
        assert reset_state is not None

        # Verify defaults are used when original state lacks connection facts
        assert reset_state.provider_id == "minimal-provider"
        assert reset_state.phase == OnboardingPhase.INIT
        assert reset_state.database_url_configured is False
        assert reset_state.connection_verified is False
        assert reset_state.dialect_detected is None
        assert reset_state.catalogs_discovered == []
        assert reset_state.schemas_discovered == []
        assert reset_state.tables_discovered == []


def test_reset_with_provider_id_override():
    """Test reset with provider_id override when no existing state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn_path = Path(tmpdir)

        # Create a state file first, then delete to test override
        temp_state = OnboardingState(provider_id="original")
        save_state(temp_state, connection_path=conn_path)

        # Load and verify it was corrupted somehow (simulate by loading None)
        # We'll patch load_state to return None to test the provider_id fallback
        import db_mcp.onboarding.state as state_module
        original_load = state_module.load_state

        def mock_load(*args, **kwargs):
            return None

        state_module.load_state = mock_load

        try:
            # Reset with provider_id override
            delete_result = delete_state(
                provider_id="override-provider", connection_path=conn_path
            )
            assert delete_result["deleted"] is True

            # Restore original load function and verify
            state_module.load_state = original_load
            reset_state = load_state(connection_path=conn_path)
            assert reset_state is not None
            assert reset_state.provider_id == "override-provider"
        finally:
            # Always restore the original function
            state_module.load_state = original_load


def test_discover_finds_connection_with_only_env_file():
    """Test that discover() finds connections with only .env files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connections_dir = Path(tmpdir)

        # Create a connection directory with only .env file
        conn_dir = connections_dir / "env-only-connection"
        conn_dir.mkdir()

        # Create .env file with DATABASE_URL
        env_file = conn_dir / ".env"
        env_file.write_text("DATABASE_URL=postgresql://user:pass@localhost/db\n")

        # Create registry and discover connections
        from db_mcp.config import Settings

        # Create settings that point to our temp directory
        settings = Settings(connections_dir=str(connections_dir))
        registry = ConnectionRegistry(settings)

        connections = registry.discover()

        # Verify the connection was discovered
        assert "env-only-connection" in connections

        conn_info = connections["env-only-connection"]
        assert conn_info.name == "env-only-connection"
        assert conn_info.type == "sql"
        assert conn_info.dialect == "postgresql"  # Should be detected from DATABASE_URL
        assert conn_info.path == conn_dir


def test_discover_skips_empty_directories():
    """Test that discover() skips directories with no valid files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connections_dir = Path(tmpdir)

        # Create empty directory
        empty_dir = connections_dir / "empty-connection"
        empty_dir.mkdir()

        # Create directory with unrelated files
        unrelated_dir = connections_dir / "unrelated-connection"
        unrelated_dir.mkdir()
        (unrelated_dir / "random.txt").write_text("not a config file")

        # Create directory with valid .env file
        valid_dir = connections_dir / "valid-connection"
        valid_dir.mkdir()
        (valid_dir / ".env").write_text("DATABASE_URL=sqlite:///test.db")

        # Create settings and registry
        from db_mcp.config import Settings
        settings = Settings(connections_dir=str(connections_dir))
        registry = ConnectionRegistry(settings)

        connections = registry.discover()

        # Should only find the valid connection
        assert len(connections) == 1
        assert "valid-connection" in connections
        assert "empty-connection" not in connections
        assert "unrelated-connection" not in connections


def test_discover_prioritizes_connector_yaml_over_env():
    """Test that connector.yaml takes precedence over .env for dialect detection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        connections_dir = Path(tmpdir)

        # Create connection with both connector.yaml and .env
        conn_dir = connections_dir / "hybrid-connection"
        conn_dir.mkdir()

        # Create .env with postgresql URL
        (conn_dir / ".env").write_text("DATABASE_URL=postgresql://user:pass@localhost/db")

        # Create connector.yaml with mysql dialect
        import yaml
        connector_config = {
            "type": "sql",
            "dialect": "mysql",
            "description": "MySQL connection from connector.yaml"
        }
        with open(conn_dir / "connector.yaml", "w") as f:
            yaml.dump(connector_config, f)

        # Create settings and registry
        from db_mcp.config import Settings
        settings = Settings(connections_dir=str(connections_dir))
        registry = ConnectionRegistry(settings)

        connections = registry.discover()

        # Verify connector.yaml takes precedence
        conn_info = connections["hybrid-connection"]
        assert conn_info.dialect == "mysql"  # From connector.yaml, not postgresql from .env
        assert conn_info.description == "MySQL connection from connector.yaml"
