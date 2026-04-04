"""Tests for create_mcp_server() factory extraction."""

from __future__ import annotations


def test_create_mcp_server_is_importable():
    """create_mcp_server must be importable from db_mcp_server.server."""
    from db_mcp_server.server import create_mcp_server

    assert callable(create_mcp_server)


def test_create_mcp_server_returns_fastmcp(monkeypatch):
    """create_mcp_server() returns a FastMCP instance."""
    monkeypatch.setenv("TOOL_MODE", "shell")
    monkeypatch.setenv("CONNECTION_NAME", "test")
    monkeypatch.setenv("CONNECTION_PATH", "/tmp/test")

    from db_mcp_server.server import create_mcp_server

    server = create_mcp_server()

    from fastmcp import FastMCP

    assert isinstance(server, FastMCP)


def test_create_mcp_server_has_http_app_method(monkeypatch):
    """The returned server must expose http_app() for ASGI mounting."""
    monkeypatch.setenv("TOOL_MODE", "shell")
    monkeypatch.setenv("CONNECTION_NAME", "test")
    monkeypatch.setenv("CONNECTION_PATH", "/tmp/test")

    from db_mcp_server.server import create_mcp_server

    server = create_mcp_server()
    assert hasattr(server, "http_app")
    assert callable(server.http_app)
