"""Configuration loader for the insider agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


def _default_config_path() -> Path:
    return Path.home() / ".db-mcp" / "config.yaml"


def _default_connection_root() -> Path:
    return Path.home() / ".db-mcp" / "connections"


def _read_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


class InsiderBudgets(BaseModel):
    max_tokens_per_run: int = 12000
    max_runs_per_hour: int = 10
    max_monthly_spend_usd: float = 25.0


class InsiderTriggers(BaseModel):
    new_connection: bool = True


class InsiderGovernance(BaseModel):
    auto_apply: list[str] = Field(
        default_factory=lambda: [
            "draft_domain_model",
            "findings",
            "example_candidates",
        ]
    )
    require_review: list[str] = Field(
        default_factory=lambda: [
            "schema_descriptions",
            "canonical_examples",
            "canonical_domain_model",
        ]
    )
    blocked: list[str] = Field(
        default_factory=lambda: [
            "connector_config",
            "delete_canonical",
        ]
    )


class InsiderConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai-compatible"
    model: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    max_concurrent_runs: int = 2
    debounce_seconds: int = 30
    budgets: InsiderBudgets = Field(default_factory=InsiderBudgets)
    triggers: InsiderTriggers = Field(default_factory=InsiderTriggers)
    governance: InsiderGovernance = Field(default_factory=InsiderGovernance)

    @model_validator(mode="after")
    def _validate_enabled_config(self) -> "InsiderConfig":
        if self.enabled and (not self.provider or not self.model):
            raise ValueError("provider and model are required when insider is enabled")
        return self


def get_insider_db_path() -> Path:
    """Return the SQLite path used by the insider subsystem."""
    override = os.environ.get("DB_MCP_INSIDER_DB", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".db-mcp" / "insider.db"


def load_insider_config(connection_path: Path | None = None) -> InsiderConfig:
    """Load global insider config and merge any connection-local override."""
    config_path = Path(os.environ.get("DB_MCP_INSIDER_CONFIG", "") or _default_config_path())
    global_cfg = _read_yaml_file(config_path).get("insider", {})
    if not isinstance(global_cfg, dict):
        global_cfg = {}

    merged: dict[str, Any] = dict(global_cfg)

    conn_path = connection_path
    if conn_path is None:
        env_path = os.environ.get("CONNECTION_PATH", "").strip()
        if env_path:
            conn_path = Path(env_path)
        else:
            connections_dir = Path(
                os.environ.get("CONNECTIONS_DIR", "") or _default_connection_root()
            )
            connection_name = os.environ.get("CONNECTION_NAME", "").strip()
            if connection_name:
                conn_path = connections_dir / connection_name

    if conn_path is not None:
        connector_cfg = _read_yaml_file(conn_path / "connector.yaml").get("insider", {})
        if isinstance(connector_cfg, dict):
            for key, value in connector_cfg.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                else:
                    merged[key] = value

    return InsiderConfig.model_validate(merged)
