from pathlib import Path
from unittest.mock import patch

import pytest

from db_mcp.tools.vault import _save_artifact


@pytest.mark.asyncio
async def test_save_artifact_tool_uses_connection_path_service_result(tmp_path: Path):
    with (
        patch(
            "db_mcp.tools.vault.resolve_connection",
            return_value=(object(), "playground", tmp_path),
        ),
        patch(
            "db_mcp.tools.vault.vault_service.save_artifact",
            return_value={
                "saved": True,
                "artifact_type": "domain_model",
                "file_path": str(tmp_path / "domain" / "model.md"),
                "error": None,
            },
        ) as mock_save,
    ):
        result = await _save_artifact(
            connection="playground",
            artifact_type="domain_model",
            content="# Domain Model\n",
        )

    assert result["saved"] is True
    mock_save.assert_called_once_with(
        connection_path=tmp_path,
        artifact_type="domain_model",
        content="# Domain Model\n",
        name=None,
    )
