import os
from unittest.mock import patch

from click.testing import CliRunner
from db_mcp_cli.main import main


def test_start_honors_preconfigured_connection_environment(monkeypatch, tmp_path):
    with patch.dict(os.environ, os.environ.copy(), clear=True):
        bench_connections_dir = tmp_path / "bench-connections"
        bench_connection_path = bench_connections_dir / "playground"
        bench_connection_path.mkdir(parents=True)
        (bench_connection_path / ".env").write_text('DATABASE_URL="sqlite:///bench.sqlite"\n')
        config_file = tmp_path / "config.yaml"
        config_file.write_text("active_connection: playground\n")

        captured: dict[str, str] = {}

        monkeypatch.setenv("CONNECTIONS_DIR", str(bench_connections_dir))
        monkeypatch.setenv("CONNECTION_PATH", str(bench_connection_path))

        monkeypatch.setattr("db_mcp_cli.commands.server_cmd.CONFIG_FILE", config_file)
        monkeypatch.setattr(
            "db_mcp_cli.commands.server_cmd.load_config",
            lambda: {"active_connection": "playground", "tool_mode": "shell", "log_level": "INFO"},
        )
        monkeypatch.setattr(
            "db_mcp_cli.commands.server_cmd.get_connection_path",
            lambda name: tmp_path / "wrong-from-cli" / name,
        )
        monkeypatch.setattr("db_mcp.migrations.run_migrations", lambda name: {"applied": []})

        import db_mcp_server.server

        def fake_server_main():
            captured["connection_path"] = os.environ["CONNECTION_PATH"]
            captured["connections_dir"] = os.environ["CONNECTIONS_DIR"]
            captured["connection_name"] = os.environ["CONNECTION_NAME"]
            captured["database_url"] = os.environ["DATABASE_URL"]

        monkeypatch.setattr(db_mcp_server.server, "main", fake_server_main)

        runner = CliRunner()
        result = runner.invoke(main, ["start", "-c", "playground"])

        assert result.exit_code == 0, result.output
        assert captured["connection_path"] == str(bench_connection_path)
        assert captured["connections_dir"] == str(bench_connections_dir)
        assert captured["connection_name"] == "playground"
        assert captured["database_url"] == "sqlite:///bench.sqlite"
