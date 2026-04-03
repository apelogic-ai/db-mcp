"""Tests for db_mcp_server.tools.vault wrapper functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_resolve():
    with patch(
        "db_mcp_server.tools.vault.resolve_connection",
        return_value=("conn", "sqlite", Path("/tmp/test")),
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_save_artifact(mock_resolve):
    with patch(
        "db_mcp_server.tools.vault.save_artifact",
        return_value={"status": "saved", "path": "examples/test.yaml"},
    ) as mock_save:
        from db_mcp_server.tools.vault import _save_artifact

        result = await _save_artifact(
            connection="mydb",
            artifact_type="example",
            content="name: test\nsql: SELECT 1",
            name="test",
        )

    assert result == {"status": "saved", "path": "examples/test.yaml"}
    mock_save.assert_called_once_with(
        connection_path=Path("/tmp/test"),
        artifact_type="example",
        content="name: test\nsql: SELECT 1",
        name="test",
    )


@pytest.mark.asyncio
async def test_vault_write(mock_resolve):
    with patch(
        "db_mcp_server.tools.vault.vault_write",
        return_value={"status": "ok"},
    ) as mock_vw:
        from db_mcp_server.tools.vault import _vault_write

        yaml_content = "tables:\n  - name: users\n"
        result = await _vault_write(
            connection="mydb",
            path="schema/descriptions.yaml",
            content=yaml_content,
        )

    assert result == {"status": "ok"}
    mock_vw.assert_called_once_with(
        connection_path=Path("/tmp/test"),
        path="schema/descriptions.yaml",
        content=yaml_content,
    )


@pytest.mark.asyncio
async def test_vault_append(mock_resolve):
    with patch(
        "db_mcp_server.tools.vault.vault_append",
        return_value={"status": "ok"},
    ) as mock_va:
        from db_mcp_server.tools.vault import _vault_append

        content = "- learned: always use LEFT JOIN for optional relations\n"
        result = await _vault_append(
            connection="mydb",
            path="learnings/joins.md",
            content=content,
        )

    assert result == {"status": "ok"}
    mock_va.assert_called_once_with(
        connection_path=Path("/tmp/test"),
        path="learnings/joins.md",
        content=content,
    )
