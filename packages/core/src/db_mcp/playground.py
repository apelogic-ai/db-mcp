"""On-demand playground connection installer.

Copies the bundled Chinook SQLite database and pre-seeded context files
into ~/.db-mcp/ for use as a demo connection.
"""

import importlib.resources
import logging
import shutil
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PLAYGROUND_CONNECTION_NAME = "playground"


def _get_data_path() -> Path:
    """Get path to bundled data files using importlib.resources."""
    ref = importlib.resources.files("db_mcp") / "data"
    return Path(str(ref))


def _get_connections_dir() -> Path:
    """Get the connections directory."""
    return Path.home() / ".db-mcp" / "connections"


def _get_data_dir() -> Path:
    """Get the shared data directory."""
    return Path.home() / ".db-mcp" / "data"


def is_playground_installed() -> bool:
    """Check if the playground connection exists."""
    playground_dir = _get_connections_dir() / PLAYGROUND_CONNECTION_NAME
    return playground_dir.exists() and (playground_dir / "connector.yaml").exists()


def install_playground() -> dict:
    """Install the playground connection on demand.

    Copies chinook.db to ~/.db-mcp/data/chinook.db (shared location),
    creates a "playground" connection with pre-seeded context files.

    Returns:
        dict with success status, connection name, and database_url.
    """
    if is_playground_installed():
        # Already installed — return existing info
        playground_dir = _get_connections_dir() / PLAYGROUND_CONNECTION_NAME
        connector_path = playground_dir / "connector.yaml"
        db_url = ""
        if connector_path.exists():
            with open(connector_path) as f:
                config = yaml.safe_load(f) or {}
                db_url = config.get("database_url", "")
        return {
            "success": True,
            "connection": PLAYGROUND_CONNECTION_NAME,
            "database_url": db_url,
            "already_installed": True,
        }

    data_path = _get_data_path()
    chinook_src = data_path / "chinook.db"
    playground_src = data_path / "playground"

    if not chinook_src.exists():
        return {"success": False, "error": f"Chinook database not found at {chinook_src}"}

    if not playground_src.exists():
        return {"success": False, "error": f"Playground data not found at {playground_src}"}

    # Copy chinook.db to shared data directory
    data_dir = _get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    chinook_dest = data_dir / "chinook.db"
    shutil.copy2(chinook_src, chinook_dest)
    logger.info(f"Copied Chinook database to {chinook_dest}")

    # Create playground connection directory with credentials ONLY
    # Do NOT copy pre-seeded context — the whole point is for the user
    # to learn the onboarding flow by going through it themselves.
    playground_dir = _get_connections_dir() / PLAYGROUND_CONNECTION_NAME
    playground_dir.mkdir(parents=True, exist_ok=True)

    # Build the database URL
    database_url = f"sqlite:///{chinook_dest}"

    # Create connector.yaml with just the connection info
    connector_path = playground_dir / "connector.yaml"
    config = {"type": "sql", "database_url": database_url}
    with open(connector_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Create .env file with DATABASE_URL
    env_file = playground_dir / ".env"
    with open(env_file, "w") as f:
        f.write("# db-mcp playground connection\n")
        f.write(f'DATABASE_URL="{database_url}"\n')

    # Create .gitignore
    gitignore_file = playground_dir / ".gitignore"
    with open(gitignore_file, "w") as f:
        f.write("# Ignore credentials\n")
        f.write(".env\n")
        f.write("# Ignore local state\n")
        f.write("state.yaml\n")

    logger.info(f"Created playground connection at {playground_dir}")

    return {
        "success": True,
        "connection": PLAYGROUND_CONNECTION_NAME,
        "database_url": database_url,
    }


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy directory contents, creating dirs as needed."""
    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            dest_item.mkdir(parents=True, exist_ok=True)
            _copy_tree(item, dest_item)
        else:
            shutil.copy2(item, dest_item)
