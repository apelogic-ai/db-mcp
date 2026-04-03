from __future__ import annotations

import json
import os
import sys
import types

import pytest
from click.testing import CliRunner
from db_mcp_cli.commands.services import (
    _configure_service_environment,
    _patch_fakeredis_for_frozen,
)
from db_mcp_cli.main import main

from db_mcp.config import reset_settings


@pytest.fixture(autouse=True)
def _reset_runtime_settings_state(monkeypatch):
    reset_settings()
    for key in ("TOOL_MODE", "RUNTIME_INTERFACE", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
        os.environ.pop(key, None)
    yield
    for key in ("TOOL_MODE", "RUNTIME_INTERFACE", "LOG_LEVEL"):
        os.environ.pop(key, None)
    reset_settings()


def test_up_starts_local_service_and_writes_state(tmp_path, monkeypatch):
    config_dir = tmp_path / ".db-mcp"
    connection_name = "demo"
    config_dir.mkdir(parents=True)

    monkeypatch.setattr("db_mcp_cli.commands.services.CONFIG_DIR", config_dir)
    monkeypatch.setenv("DB_MCP_LOCAL_SERVICE_STATE", str(config_dir / "local-service.json"))
    monkeypatch.setattr(
        "db_mcp_cli.commands.services._configure_service_environment",
        lambda connection, **_: connection_name,
    )
    monkeypatch.setattr("db_mcp_cli.commands.services.clear_local_service_state", lambda: None)

    captured: dict[str, object] = {}

    def fake_start_ui_background_service(*, host: str, port: int, verbose: bool) -> None:
        captured["ui"] = {"host": host, "port": port, "verbose": verbose}

    def fake_run_http_mcp_service(*, host: str, port: int, path: str) -> None:
        captured["mcp"] = {"host": host, "port": port, "path": path}

    monkeypatch.setattr(
        "db_mcp_cli.commands.services._start_ui_background_service",
        fake_start_ui_background_service,
    )
    monkeypatch.setattr(
        "db_mcp_cli.commands.services._run_http_mcp_service",
        fake_run_http_mcp_service,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "up",
            "--ui-host",
            "127.0.0.1",
            "--ui-port",
            "8088",
            "--mcp-host",
            "127.0.0.1",
            "--mcp-port",
            "8099",
            "--mcp-path",
            "/mcp",
        ],
    )

    assert result.exit_code == 0
    assert captured["ui"] == {"host": "127.0.0.1", "port": 8088, "verbose": False}
    assert captured["mcp"] == {"host": "127.0.0.1", "port": 8099, "path": "/mcp"}

    state_path = config_dir / "local-service.json"
    payload = json.loads(state_path.read_text())
    assert payload["connection"] == connection_name
    assert payload["ui_url"] == "http://127.0.0.1:8088"
    assert payload["mcp_url"] == "http://127.0.0.1:8099/mcp"


def test_configure_service_environment_can_force_runtime_surface(tmp_path, monkeypatch):
    reset_settings()
    config_dir = tmp_path / ".db-mcp"
    connections_dir = config_dir / "connections"
    config_dir.mkdir(parents=True)
    connections_dir.mkdir(parents=True)

    monkeypatch.setattr("db_mcp_cli.commands.services.CONFIG_DIR", config_dir)
    monkeypatch.setattr("db_mcp_cli.commands.services.CONNECTIONS_DIR", connections_dir)
    monkeypatch.setattr(
        "db_mcp_cli.commands.services.CONFIG_FILE",
        config_dir / "config.json",
    )
    (config_dir / "config.json").write_text("{}")
    monkeypatch.setattr(
        "db_mcp_cli.commands.services.load_config",
        lambda: {
            "active_connection": "demo",
            "tool_mode": "shell",
            "log_level": "DEBUG",
            "runtime_interface": "cli",
        },
    )
    monkeypatch.setattr(
        "db_mcp_cli.commands.services._load_connection_env",
        lambda connection: {"DATABASE_URL": "sqlite:///demo.db"},
    )
    monkeypatch.setattr(
        "db_mcp_cli.commands.services.get_connection_path",
        lambda connection: connections_dir / connection,
    )

    monkeypatch.setattr(
        "db_mcp.migrations.run_migrations",
        lambda connection: {"applied": []},
    )
    monkeypatch.setattr(
        "db_mcp.migrations.run_migrations_all",
        lambda: [],
    )

    monkeypatch.delenv("TOOL_MODE", raising=False)
    monkeypatch.delenv("RUNTIME_INTERFACE", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    try:
        conn_name = _configure_service_environment(
            None,
            tool_mode_override="code",
            runtime_interface_override="native",
        )

        assert conn_name == "demo"
        assert os.environ["TOOL_MODE"] == "code"
        assert os.environ["RUNTIME_INTERFACE"] == "native"
        assert os.environ["LOG_LEVEL"] == "DEBUG"
    finally:
        reset_settings()


def test_patch_fakeredis_for_frozen_uses_bundle_commands_json(tmp_path, monkeypatch):
    fakeredis_pkg = types.ModuleType("fakeredis")
    fakeredis_pkg.__path__ = []  # type: ignore[attr-defined]
    model_pkg = types.ModuleType("fakeredis.model")
    model_pkg.__path__ = []  # type: ignore[attr-defined]
    command_info = types.ModuleType("fakeredis.model._command_info")
    command_info._COMMAND_INFO = None
    command_info._encode_obj = lambda obj: {"loaded": obj}

    bundle_dir = tmp_path / "bundle" / "fakeredis"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "commands.json").write_text('{"PING": {"name": "PING"}}')

    monkeypatch.setitem(sys.modules, "fakeredis", fakeredis_pkg)
    monkeypatch.setitem(sys.modules, "fakeredis.model", model_pkg)
    monkeypatch.setitem(sys.modules, "fakeredis.model._command_info", command_info)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    _patch_fakeredis_for_frozen()
    command_info._load_command_info()

    assert command_info._COMMAND_INFO == {"loaded": {"PING": {"name": "PING"}}}
