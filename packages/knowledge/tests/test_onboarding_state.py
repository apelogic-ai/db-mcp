"""Tests for onboarding state persistence."""


from db_mcp_models import OnboardingPhase

from db_mcp_knowledge.onboarding.state import (
    create_initial_state,
    delete_state,
    load_state,
    save_state,
)


def test_create_initial_state():
    """Test creating initial onboarding state."""
    state = create_initial_state("test-provider")

    assert state.provider_id == "test-provider"
    assert state.phase == OnboardingPhase.NOT_STARTED
    assert state.started_at is not None
    assert state.database_url_configured is False
    assert state.tables_total == 0


def test_save_and_load_state(tmp_path):
    """Test saving and loading state."""
    state = create_initial_state("test-provider")
    state.phase = OnboardingPhase.INIT
    state.database_url_configured = True
    state.dialect_detected = "postgresql"

    result = save_state(state, tmp_path)
    assert result["saved"] is True
    assert result["error"] is None

    # Verify file exists
    state_file = tmp_path / "state.yaml"
    assert state_file.exists()

    # Load and verify
    loaded = load_state("test-provider", connection_path=tmp_path)
    assert loaded is not None
    assert loaded.provider_id == "test-provider"
    assert loaded.phase == OnboardingPhase.INIT
    assert loaded.database_url_configured is True
    assert loaded.dialect_detected == "postgresql"


def test_load_nonexistent_state(tmp_path):
    """Test loading state that doesn't exist."""
    loaded = load_state("nonexistent-provider", connection_path=tmp_path)
    assert loaded is None


def test_delete_state(tmp_path):
    """Test deleting state."""
    state = create_initial_state("test-provider")
    save_state(state, tmp_path)

    # Verify exists
    assert load_state("test-provider", connection_path=tmp_path) is not None

    # Delete (use legacy behavior for unit test)
    result = delete_state(tmp_path, preserve_connection=False)
    assert result["deleted"] is True

    # Verify deleted
    assert load_state("test-provider", connection_path=tmp_path) is None


def test_delete_nonexistent_state(tmp_path):
    """Test deleting state that doesn't exist."""
    result = delete_state(tmp_path)
    assert result["deleted"] is False
    assert "not found" in result["error"]


def test_state_progress_calculation():
    """Test progress percentage calculation."""
    state = create_initial_state("test")

    # Not started
    assert state.progress_percentage() == 0

    # Init phase
    state.phase = OnboardingPhase.INIT
    assert state.progress_percentage() == 10

    # Schema phase with progress (tables_described is now passed as arg)
    state.phase = OnboardingPhase.SCHEMA
    state.tables_total = 10
    progress = state.progress_percentage(tables_described=5)
    assert 10 < progress <= 40

    # Schema phase with no progress
    progress_zero = state.progress_percentage(tables_described=0)
    assert progress_zero == 10  # base for SCHEMA phase
