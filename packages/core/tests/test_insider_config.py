"""Tests for insider-agent config loading."""


import yaml

from db_mcp.insider.config import load_insider_config


def test_load_insider_config_merges_global_and_connection_override(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "insider": {
                    "enabled": True,
                    "provider": "anthropic",
                    "model": "global-model",
                    "debounce_seconds": 10,
                    "budgets": {"max_runs_per_hour": 3},
                }
            }
        )
    )
    connection_path = tmp_path / "connections" / "playground"
    connection_path.mkdir(parents=True)
    (connection_path / "connector.yaml").write_text(
        yaml.dump(
            {
                "insider": {
                    "model": "connection-model",
                    "budgets": {"max_tokens_per_run": 999},
                }
            }
        )
    )
    monkeypatch.setenv("DB_MCP_INSIDER_CONFIG", str(config_path))

    cfg = load_insider_config(connection_path)

    assert cfg.enabled is True
    assert cfg.model == "connection-model"
    assert cfg.debounce_seconds == 10
    assert cfg.budgets.max_runs_per_hour == 3
    assert cfg.budgets.max_tokens_per_run == 999
