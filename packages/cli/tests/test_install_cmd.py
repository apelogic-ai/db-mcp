"""Tests for db-mcp uninstall and update commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from db_mcp_cli.commands import install_cmd
from db_mcp_cli.main import main

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_install(tmp_path, monkeypatch):
    """Build a sandbox: ~/.db-mcp under tmp_path and a fake installed binary."""
    config_dir = tmp_path / ".db-mcp"
    cache_dir = config_dir / "cache"
    cache_dir.mkdir(parents=True)
    install_dir = tmp_path / ".local" / "bin"
    install_dir.mkdir(parents=True)

    cached = cache_dir / "db-mcp-0.9.11"
    cached.write_bytes(b"#!/bin/sh\nexit 0\n")
    cached.chmod(0o755)

    binary = install_dir / "db-mcp"
    binary.symlink_to(cached)

    # Some content under the config dir to verify --purge actually wipes it.
    (config_dir / "config.yaml").write_text("active_connection: dev\n")
    (config_dir / "connections").mkdir()
    (config_dir / "connections" / "dev").mkdir()
    (config_dir / "connections" / "dev" / ".env").write_text("DATABASE_URL=sqlite:///x\n")

    monkeypatch.setenv("DB_MCP_INSTALL", str(install_dir))
    monkeypatch.setattr(install_cmd, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(install_cmd, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(install_cmd, "DEFAULT_INSTALL_DIR", install_dir)

    return {
        "config_dir": config_dir,
        "cache_dir": cache_dir,
        "install_dir": install_dir,
        "binary": binary,
        "cached": cached,
    }


# ---------------------------------------------------------------------------
# _detect_platform / _resolve_binary_path
# ---------------------------------------------------------------------------


def test_detect_platform_macos_arm64(monkeypatch):
    monkeypatch.setattr(install_cmd.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(install_cmd.platform, "machine", lambda: "arm64")
    assert install_cmd._detect_platform() == "macos-arm64"


def test_detect_platform_linux_x64(monkeypatch):
    monkeypatch.setattr(install_cmd.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install_cmd.platform, "machine", lambda: "x86_64")
    assert install_cmd._detect_platform() == "linux-x64"


def test_detect_platform_unsupported_arch(monkeypatch):
    monkeypatch.setattr(install_cmd.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install_cmd.platform, "machine", lambda: "riscv64")
    with pytest.raises(install_cmd.click.ClickException):
        install_cmd._detect_platform()


def test_resolve_binary_path_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_MCP_INSTALL", str(tmp_path))
    assert install_cmd._resolve_binary_path() == tmp_path / "db-mcp"


def test_resolve_binary_path_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DB_MCP_INSTALL", raising=False)
    monkeypatch.setattr(install_cmd.sys, "argv", [""])
    monkeypatch.setattr(install_cmd.shutil, "which", lambda _: None)
    fake_default = Path("/tmp/fake-bin")
    monkeypatch.setattr(install_cmd, "DEFAULT_INSTALL_DIR", fake_default)
    assert install_cmd._resolve_binary_path() == fake_default / "db-mcp"


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


def test_uninstall_requires_confirmation_when_no_yes(fake_install):
    runner = CliRunner()
    # Provide "n" to the confirmation; binary should remain.
    result = runner.invoke(main, ["uninstall"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output
    assert fake_install["binary"].is_symlink()
    assert fake_install["cached"].exists()


def test_uninstall_removes_binary_only(fake_install):
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall", "-y"])
    assert result.exit_code == 0, result.output
    assert not fake_install["binary"].exists()
    assert not fake_install["binary"].is_symlink()
    assert not fake_install["cached"].exists()
    # Config dir must remain untouched without --purge.
    assert fake_install["config_dir"].exists()
    assert (fake_install["config_dir"] / "config.yaml").exists()


def test_uninstall_purge_removes_config(fake_install):
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall", "--purge", "-y"])
    assert result.exit_code == 0, result.output
    assert not fake_install["binary"].exists()
    assert not fake_install["config_dir"].exists()


def test_uninstall_purge_double_confirmation(fake_install):
    """First prompt 'y', second prompt 'n' must abort and keep the config."""
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall", "--purge"], input="y\nn\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output
    # Binary preserved (uninstall not yet performed when second prompt declined).
    assert fake_install["binary"].is_symlink()
    assert fake_install["config_dir"].exists()


def test_uninstall_purge_double_confirmation_both_yes(fake_install):
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall", "--purge"], input="y\ny\n")
    assert result.exit_code == 0, result.output
    assert not fake_install["binary"].exists()
    assert not fake_install["config_dir"].exists()


def test_uninstall_missing_binary_without_purge(fake_install):
    fake_install["binary"].unlink()
    fake_install["cached"].unlink()
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall", "-y"])
    assert result.exit_code == 0
    assert "No db-mcp binary found" in result.output
    # Without --purge, missing binary returns early and config stays.
    assert fake_install["config_dir"].exists()


def test_uninstall_purge_when_binary_missing(fake_install):
    fake_install["binary"].unlink()
    fake_install["cached"].unlink()
    runner = CliRunner()
    result = runner.invoke(main, ["uninstall", "--purge", "-y"])
    assert result.exit_code == 0, result.output
    assert not fake_install["config_dir"].exists()


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_check_already_latest(fake_install):
    with patch.object(install_cmd, "_get_cli_version", return_value="0.9.11"), \
         patch.object(install_cmd, "_fetch_latest_version", return_value="0.9.11"):
        runner = CliRunner()
        result = runner.invoke(main, ["update", "--check"])
    assert result.exit_code == 0
    assert "Already up to date" in result.output


def test_update_check_available(fake_install):
    with patch.object(install_cmd, "_get_cli_version", return_value="0.9.10"), \
         patch.object(install_cmd, "_fetch_latest_version", return_value="0.9.11"):
        runner = CliRunner()
        result = runner.invoke(main, ["update", "--check"])
    assert result.exit_code == 0
    assert "Update available" in result.output
    assert "0.9.10" in result.output and "0.9.11" in result.output


def test_update_install_calls_install_binary(fake_install):
    with patch.object(install_cmd, "_get_cli_version", return_value="0.9.10"), \
         patch.object(install_cmd, "_fetch_latest_version", return_value="0.9.11"), \
         patch.object(install_cmd, "_install_binary") as mock_install:
        mock_install.return_value = fake_install["binary"]
        runner = CliRunner()
        result = runner.invoke(main, ["update", "-y"])
    assert result.exit_code == 0, result.output
    mock_install.assert_called_once()
    # First positional arg is the version.
    assert mock_install.call_args.args[0] == "0.9.11"


def test_update_aborts_when_user_declines(fake_install):
    with patch.object(install_cmd, "_get_cli_version", return_value="0.9.10"), \
         patch.object(install_cmd, "_fetch_latest_version", return_value="0.9.11"), \
         patch.object(install_cmd, "_install_binary") as mock_install:
        runner = CliRunner()
        result = runner.invoke(main, ["update"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output
    mock_install.assert_not_called()


def test_update_explicit_version_skips_fetch(fake_install):
    with patch.object(install_cmd, "_get_cli_version", return_value="0.9.10"), \
         patch.object(install_cmd, "_fetch_latest_version") as fetch, \
         patch.object(install_cmd, "_install_binary") as mock_install:
        runner = CliRunner()
        result = runner.invoke(main, ["update", "--version", "0.8.7", "-y"])
    assert result.exit_code == 0, result.output
    fetch.assert_not_called()
    mock_install.assert_called_once()
    assert mock_install.call_args.args[0] == "0.8.7"


def test_update_explicit_version_strips_v_prefix(fake_install):
    with patch.object(install_cmd, "_get_cli_version", return_value="0.9.10"), \
         patch.object(install_cmd, "_install_binary") as mock_install:
        runner = CliRunner()
        result = runner.invoke(main, ["update", "--version", "v0.9.11", "-y"])
    assert result.exit_code == 0, result.output
    assert mock_install.call_args.args[0] == "0.9.11"


def test_update_fails_when_github_unreachable(fake_install):
    with patch.object(install_cmd, "_fetch_latest_version", return_value=None):
        runner = CliRunner()
        result = runner.invoke(main, ["update"])
    assert result.exit_code != 0
    assert "Could not contact GitHub" in result.output


# ---------------------------------------------------------------------------
# _install_binary (integration-ish; mocks the network layer)
# ---------------------------------------------------------------------------


def test_install_binary_macos_creates_symlink(fake_install, monkeypatch):
    monkeypatch.setattr(install_cmd, "_detect_platform", lambda: "macos-arm64")

    def fake_download(url, dest, timeout=60.0):
        dest.write_bytes(b"new-binary-bytes")

    monkeypatch.setattr(install_cmd, "_download_to", fake_download)

    binary = fake_install["binary"]
    install_cmd._install_binary("0.9.12", binary)

    new_cached = fake_install["cache_dir"] / "db-mcp-0.9.12"
    assert new_cached.exists()
    assert binary.is_symlink()
    assert binary.resolve() == new_cached.resolve()


def test_install_binary_linux_writes_directly(fake_install, monkeypatch):
    monkeypatch.setattr(install_cmd, "_detect_platform", lambda: "linux-x64")

    fake_install["binary"].unlink()  # start from empty
    written = []

    def fake_download(url, dest, timeout=60.0):
        written.append(dest)
        dest.write_bytes(b"new-binary-bytes")

    monkeypatch.setattr(install_cmd, "_download_to", fake_download)

    install_cmd._install_binary("0.9.12", fake_install["binary"])
    assert fake_install["binary"].exists()
    assert not fake_install["binary"].is_symlink()
    assert written == [fake_install["binary"]]


def test_fetch_latest_version_handles_network_error(monkeypatch):
    import urllib.error

    def boom(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(install_cmd.urllib.request, "urlopen", boom)
    assert install_cmd._fetch_latest_version() is None


def test_fetch_latest_version_parses_tag(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"tag_name": "v1.2.3"}'

    def fake_open(req, timeout=5.0):
        return FakeResp()

    # urllib.request.json.load reads from the response object; emulate it.
    import json as _json

    monkeypatch.setattr(install_cmd.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(install_cmd.json, "load", lambda f: _json.loads(f.read()))
    assert install_cmd._fetch_latest_version() == "1.2.3"
