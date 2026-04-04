"""Tests for TUI welcome message and expanded command set."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_welcome_message_shown_on_startup():
    """Feed should contain a welcome message after mount."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        await pilot.pause()
        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count >= 1  # welcome is an event


@pytest.mark.asyncio
async def test_connections_command():
    """/connections should list connections via REST API."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.client.list_connections = MagicMock(
            return_value=[
                {"name": "mydb", "active": True},
                {"name": "other", "active": False},
            ]
        )
        await pilot.app.dispatch_command("/connections")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        # welcome + connections output
        assert feed.event_count >= 2


@pytest.mark.asyncio
async def test_schema_command():
    """/schema should show tables via REST API."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.client.list_tables = MagicMock(
            return_value=["users", "orders", "products"]
        )
        await pilot.app.dispatch_command("/schema")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count >= 2


@pytest.mark.asyncio
async def test_rules_command():
    """/rules should show business rules."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.client.list_rules = MagicMock(return_value=["churn = cancel rate"])
        await pilot.app.dispatch_command("/rules")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count >= 2


@pytest.mark.asyncio
async def test_agent_command_shows_status():
    """/agent should show agent connection status."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        await pilot.app.dispatch_command("/agent")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count >= 2  # welcome + agent status


@pytest.mark.asyncio
async def test_palette_includes_new_commands():
    """The command palette should include CLI and ACP commands."""
    from db_mcp_cli.tui.widgets.input import COMMANDS

    names = [name for name, _ in COMMANDS]
    assert "/connections" in names
    assert "/schema" in names
    assert "/rules" in names
    assert "/agent" in names
