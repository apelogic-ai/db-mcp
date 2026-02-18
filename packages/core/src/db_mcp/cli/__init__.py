"""db-mcp CLI package.

Re-exports `main` (the click group) and all public symbols from the
original cli.py so that existing imports continue to work:

    from db_mcp.cli import main
    from db_mcp.cli import list_connections
    from db_mcp.cli import CONFIG_FILE, load_config, save_config
    ...
"""

# ── Click entry point ──────────────────────────────────────────────────────────
# ── Agent configuration ────────────────────────────────────────────────────────
from db_mcp.cli.agent_config import (
    _configure_agents,
    _configure_agents_interactive,
    _configure_claude_desktop,
    extract_database_url_from_claude_config,
)

# ── Connection ─────────────────────────────────────────────────────────────────
from db_mcp.cli.connection import (
    _get_connection_env_path,
    _load_connection_env,
    _prompt_and_save_database_url,
    _save_connection_env,
    connection_exists,
    get_active_connection,
    get_connection_path,
    list_connections,
    set_active_connection,
)

# ── Schema discovery ───────────────────────────────────────────────────────────
from db_mcp.cli.discovery import _run_discovery_with_progress

# ── Git operations ─────────────────────────────────────────────────────────────
from db_mcp.cli.git_ops import (
    GIT_INSTALL_URL,
    GITIGNORE_CONTENT,
    git_clone,
    git_init,
    git_pull,
    git_sync,
    is_git_installed,
    is_git_repo,
    is_git_url,
)

# ── Init flows ─────────────────────────────────────────────────────────────────
from db_mcp.cli.init_flow import (
    _attach_repo,
    _auto_register_collaborator,
    _init_brownfield,
    _init_greenfield,
    _offer_git_setup,
    _recover_onboarding_state,
)
from db_mcp.cli.main import main

# ── Utils ─────────────────────────────────────────────────────────────────────
from db_mcp.cli.utils import (
    CONFIG_DIR,
    CONFIG_FILE,
    CONNECTIONS_DIR,
    LEGACY_PROVIDERS_DIR,
    LEGACY_VAULT_DIR,
    _get_cli_version,
    _handle_sigint,
    console,
    get_claude_desktop_config_path,
    get_db_mcp_binary_path,
    is_claude_desktop_installed,
    launch_claude_desktop,
    load_claude_desktop_config,
    load_config,
    save_claude_desktop_config,
    save_config,
)

__all__ = [
    # Entry point
    "main",
    # Utils
    "CONFIG_DIR",
    "CONFIG_FILE",
    "CONNECTIONS_DIR",
    "LEGACY_PROVIDERS_DIR",
    "LEGACY_VAULT_DIR",
    "_get_cli_version",
    "_handle_sigint",
    "console",
    "get_claude_desktop_config_path",
    "get_db_mcp_binary_path",
    "is_claude_desktop_installed",
    "launch_claude_desktop",
    "load_claude_desktop_config",
    "load_config",
    "save_claude_desktop_config",
    "save_config",
    # Connection
    "_get_connection_env_path",
    "_load_connection_env",
    "_prompt_and_save_database_url",
    "_save_connection_env",
    "connection_exists",
    "get_active_connection",
    "get_connection_path",
    "list_connections",
    "set_active_connection",
    # Git
    "GIT_INSTALL_URL",
    "GITIGNORE_CONTENT",
    "git_clone",
    "git_init",
    "git_pull",
    "git_sync",
    "is_git_installed",
    "is_git_repo",
    "is_git_url",
    # Agent config
    "_configure_agents",
    "_configure_agents_interactive",
    "_configure_claude_desktop",
    "extract_database_url_from_claude_config",
    # Discovery
    "_run_discovery_with_progress",
    # Init flows
    "_attach_repo",
    "_auto_register_collaborator",
    "_init_brownfield",
    "_init_greenfield",
    "_offer_git_setup",
    "_recover_onboarding_state",
]
