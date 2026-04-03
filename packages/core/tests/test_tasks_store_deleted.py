"""Verify tasks/ directory is fully deleted; execution/query_store is the only path."""

import importlib
import importlib.util


def test_tasks_store_module_no_longer_exists():
    """tasks/store.py must be deleted — callers should use execution/query_store."""
    try:
        spec = importlib.util.find_spec("db_mcp.tasks.store")
    except ModuleNotFoundError:
        # Parent package db_mcp.tasks is also gone — even better.
        spec = None
    assert spec is None, (
        "db_mcp.tasks.store still exists. "
        "Delete tasks/store.py and migrate callers to db_mcp.execution.query_store."
    )


def test_tasks_package_itself_no_longer_exists():
    """The entire db_mcp.tasks package must be deleted.

    tasks/__init__.py was a backward-compat re-export shim.  All callers have
    been migrated to db_mcp.execution.query_store; the shim is step 2.13 cleanup.
    """
    spec = importlib.util.find_spec("db_mcp.tasks")
    assert spec is None, (
        "db_mcp.tasks still exists as a package stub. "
        "Delete tasks/__init__.py (the backward-compat shim is no longer needed)."
    )


def test_execution_query_store_exports_query():
    from db_mcp_data.execution.query_store import Query
    assert Query is not None


def test_execution_query_store_exports_query_status():
    from db_mcp_data.execution.query_store import QueryStatus
    assert QueryStatus is not None


def test_execution_query_store_exports_query_store():
    from db_mcp_data.execution.query_store import QueryStore
    assert QueryStore is not None


def test_execution_query_store_exports_get_query_store():
    from db_mcp_data.execution.query_store import get_query_store
    assert callable(get_query_store)



def test_no_production_code_imports_from_tasks_store():
    """Verify known production modules no longer import from db_mcp.tasks.store."""
    import db_mcp.services.query as query_mod
    import db_mcp.tools.generation as gen_mod

    for mod in (query_mod, gen_mod):
        src = importlib.util.find_spec(mod.__name__)
        if src and src.origin:
            source = open(src.origin).read()
            assert "from db_mcp.tasks.store" not in source, (
                f"{mod.__name__} still imports from db_mcp.tasks.store"
            )
            assert "import db_mcp.tasks.store" not in source, (
                f"{mod.__name__} still imports from db_mcp.tasks.store"
            )
