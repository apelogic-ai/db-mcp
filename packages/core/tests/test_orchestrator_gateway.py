"""Tests that orchestrator/engine.py uses services/query.py, not tools/generation.py."""




def test_orchestrator_imports_from_services_not_tools():
    """engine.py must import run_sql/validate_sql from services, not tools."""
    import db_mcp.orchestrator.engine as engine

    # The module should expose run_sql and validate_sql bound from services
    assert hasattr(engine, "run_sql"), "engine must expose run_sql from services/query"
    assert hasattr(engine, "validate_sql"), "engine must expose validate_sql from services/query"

    # Must NOT expose the old private names
    assert not hasattr(engine, "_run_sql"), \
        "engine._run_sql still present — import not updated to services"
    assert not hasattr(engine, "_validate_sql"), \
        "engine._validate_sql still present — import not updated to services"


def test_orchestrator_run_sql_is_from_services():
    """engine.run_sql must be the same object as services.query.run_sql."""
    from db_mcp.orchestrator import engine
    from db_mcp.services.query import run_sql

    assert engine.run_sql is run_sql


def test_orchestrator_validate_sql_is_from_services():
    """engine.validate_sql must be the same object as services.query.validate_sql."""
    from db_mcp.orchestrator import engine
    from db_mcp.services.query import validate_sql

    assert engine.validate_sql is validate_sql
