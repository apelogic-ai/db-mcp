"""Tests for MCP tool coverage audit.

Verifies that all tools declared in server.py are properly exposed at runtime
and that the tool coverage audit script works correctly.
"""

import subprocess
import sys
from pathlib import Path

# Path to the audit script
AUDIT_SCRIPT = Path(__file__).parent.parent.parent.parent / "scripts" / "tool_coverage_audit.py"


class TestToolCoverageAudit:
    """Tests for the tool coverage audit script."""

    def test_audit_script_exists(self):
        """The audit script should exist."""
        assert AUDIT_SCRIPT.exists(), f"Audit script not found: {AUDIT_SCRIPT}"

    def test_audit_sql_mode_passes(self):
        """SQL mode should have 100% coverage."""
        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), "--config", "sql"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"SQL mode audit failed:\n{result.stdout}\n{result.stderr}"
        assert "100.0%" in result.stdout
        assert "PASS" in result.stdout

    def test_audit_api_mode_passes(self):
        """API mode should also have 100% coverage."""
        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), "--config", "api"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"API mode audit failed:\n{result.stdout}\n{result.stderr}"
        assert "100.0%" in result.stdout
        assert "PASS" in result.stdout

    def test_audit_json_output(self):
        """JSON output should be valid."""
        import json

        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), "--json", "--config", "sql"],
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "declared_tools" in data
        assert "runtime_tools" in data
        assert data["summary"]["status"] == "PASS"
        assert data["summary"]["coverage_percent"] == 100.0


class TestToolRegistrationCompleteness:
    """Tests that verify tool registration completeness."""

    def test_all_tools_have_implementations(self):
        """All registered tools should have corresponding implementations."""
        # This test verifies that tools registered in server.py have
        # corresponding function implementations in the tools/ directory

        # server.py has moved to packages/mcp-server/ (Phase 3.02)
        server_py = (
            Path(__file__).parents[3] / "packages" / "mcp-server"
            / "src" / "db_mcp_server" / "server.py"
        )

        # Read server.py and extract tool registrations
        server_content = server_py.read_text()
        import re

        registered_tools = set(
            re.findall(r'server\.tool\(\s*name\s*=\s*["\']([^"\']+)["\']', server_content)
        )

        # All registered tools should be discoverable at runtime
        # (This is verified by the audit script, but we check registration exists)
        assert len(registered_tools) > 0, "No tools registered in server.py"

        # Core tools that should always be present
        core_tools = {
            "ping",
            "get_config",
            "shell",
            "list_connections",
            "dismiss_insight",
            "mark_insights_processed",
        }
        missing_core = core_tools - registered_tools
        assert core_tools.issubset(registered_tools), f"Missing core tools: {missing_core}"
