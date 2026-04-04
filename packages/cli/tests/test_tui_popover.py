"""Tests for slash-command autocomplete popover."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_palette_hidden_by_default():
    """CommandPalette should be hidden on startup."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.input import CommandPalette

    async with DBMcpTUI().run_test() as pilot:
        palette = pilot.app.query_one(CommandPalette)
        assert not palette.has_class("visible")


@pytest.mark.asyncio
async def test_palette_shows_on_slash():
    """Typing '/' should show the palette with all commands."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.input import COMMANDS, CommandPalette

    async with DBMcpTUI().run_test() as pilot:
        await pilot.press("/")
        await pilot.pause()

        palette = pilot.app.query_one(CommandPalette)
        assert palette.has_class("visible")
        assert palette.option_count == len(COMMANDS)


@pytest.mark.asyncio
async def test_palette_filters_on_typing():
    """Typing '/co' should filter to /confirm only."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.input import CommandPalette

    async with DBMcpTUI().run_test() as pilot:
        await pilot.press("/", "c", "o")
        await pilot.pause()

        palette = pilot.app.query_one(CommandPalette)
        assert palette.has_class("visible")
        assert palette.option_count == 1  # /confirm


@pytest.mark.asyncio
async def test_palette_hides_on_non_slash():
    """Typing regular text should not show the palette."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.input import CommandPalette

    async with DBMcpTUI().run_test() as pilot:
        await pilot.press("h", "e", "l")
        await pilot.pause()

        palette = pilot.app.query_one(CommandPalette)
        assert not palette.has_class("visible")


@pytest.mark.asyncio
async def test_palette_hides_on_no_match():
    """Typing '/xyz' with no matches should hide the palette."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.input import CommandPalette

    async with DBMcpTUI().run_test() as pilot:
        await pilot.press("/", "x", "y", "z")
        await pilot.pause()

        palette = pilot.app.query_one(CommandPalette)
        assert not palette.has_class("visible")
