"""Core config access — re-exports from db_mcp_cli when available.

Production code in the core package (traces.py, benchmark/) uses CONFIG_FILE,
load_config, and save_config.  When db_mcp_cli is installed these come from
the CLI package; otherwise minimal stubs are provided.

For CLI-specific functions (console, get_db_mcp_binary_path, etc.) import
from db_mcp_cli directly.
"""

try:
    from db_mcp_cli import (  # noqa: F401
        CONFIG_DIR,
        CONFIG_FILE,
        CONNECTIONS_DIR,
        LEGACY_PROVIDERS_DIR,
        LEGACY_VAULT_DIR,
        _auto_register_collaborator,
        load_config,
        save_config,
    )
except ImportError:
    from pathlib import Path

    import yaml

    CONFIG_DIR = Path.home() / ".db-mcp"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"
    CONNECTIONS_DIR = CONFIG_DIR / "connections"
    LEGACY_VAULT_DIR = CONFIG_DIR / "vault"
    LEGACY_PROVIDERS_DIR = CONFIG_DIR / "providers"

    def load_config() -> dict:
        if not CONFIG_FILE.exists():
            return {}
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}

    def save_config(config: dict) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
