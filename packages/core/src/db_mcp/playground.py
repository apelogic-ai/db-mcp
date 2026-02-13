"""Auto-create playground connection for first-time users.

When no connections exist, copies the bundled Chinook SQLite database
and pre-seeded context files into ~/.db-mcp/connections/playground/.
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
    # For Python 3.9+ with importlib.resources.files
    ref = importlib.resources.files("db_mcp") / "data"
    # Materialize to a real path
    return Path(str(ref))


def _get_connections_dir() -> Path:
    """Get the connections directory."""
    return Path.home() / ".db-mcp" / "connections"


def maybe_create_playground() -> bool:
    """Create playground connection if no connections exist.

    Returns:
        True if playground was created, False otherwise.
    """
    connections_dir = _get_connections_dir()

    # If connections dir exists and has any subdirectories, skip
    if connections_dir.exists():
        existing = [p for p in connections_dir.iterdir() if p.is_dir()]
        if existing:
            logger.debug(
                f"Connections already exist ({len(existing)}), skipping playground creation"
            )
            return False

    # Create playground
    data_path = _get_data_path()
    chinook_src = data_path / "chinook.db"
    playground_src = data_path / "playground"

    if not chinook_src.exists():
        logger.warning(f"Chinook database not found at {chinook_src}, skipping playground")
        return False

    if not playground_src.exists():
        logger.warning(f"Playground data not found at {playground_src}, skipping playground")
        return False

    playground_dir = connections_dir / PLAYGROUND_CONNECTION_NAME
    playground_dir.mkdir(parents=True, exist_ok=True)

    # Copy chinook.db
    chinook_dest = playground_dir / "chinook.db"
    shutil.copy2(chinook_src, chinook_dest)
    logger.info(f"Copied Chinook database to {chinook_dest}")

    # Copy all pre-seeded context files
    _copy_tree(playground_src, playground_dir)

    # Update connector.yaml with the actual absolute path
    connector_path = playground_dir / "connector.yaml"
    if connector_path.exists():
        with open(connector_path) as f:
            config = yaml.safe_load(f)
        config["database_url"] = f"sqlite:///{chinook_dest}"
        with open(connector_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Create standard vault directories that aren't in the pre-seeded data
    for subdir in ["learnings/failures", "metrics"]:
        (playground_dir / subdir).mkdir(parents=True, exist_ok=True)

    logger.info(f"Created playground connection at {playground_dir}")
    return True


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy directory contents, creating dirs as needed."""
    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            dest_item.mkdir(parents=True, exist_ok=True)
            _copy_tree(item, dest_item)
        else:
            shutil.copy2(item, dest_item)
