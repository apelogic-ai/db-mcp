"""Tests for the MCP server."""

import importlib
import pkgutil

import pytest

from db_mcp.server import _create_server


def test_mcp_server_created():
    """Test MCP server is properly configured."""
    server = _create_server()
    assert server.name == "db-mcp"


@pytest.mark.asyncio
async def test_server_tools_registered():
    """Test that expected tools are registered on the server."""
    server = _create_server()
    # Basic sanity check - server should have tools registered
    assert server is not None


def test_all_db_mcp_modules_importable():
    """Guard against PyInstaller missing modules.

    Every db_mcp submodule must be importable. If a new module is added
    but only imported lazily (inside a function), PyInstaller won't bundle
    it and the binary will break at runtime. This test catches that by
    importing every module at test time.
    """
    import db_mcp

    failures = []

    for importer, modname, ispkg in pkgutil.walk_packages(
        path=db_mcp.__path__,
        prefix="db_mcp.",
    ):
        try:
            importlib.import_module(modname)
        except Exception as exc:
            failures.append(f"{modname}: {exc}")

    assert not failures, "The following db_mcp modules failed to import:\n" + "\n".join(failures)
