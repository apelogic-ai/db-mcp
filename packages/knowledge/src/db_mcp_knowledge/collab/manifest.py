"""Collaboration manifest model and persistence.

The manifest (.collab.yaml) lives in the connection directory and tracks
team members, roles, and sync configuration. It is checked into git so
all participants share the same member list.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ".collab.yaml"


class CollabMember(BaseModel):
    """A participant in the collaborative vault."""

    user_name: str
    user_id: str
    role: Literal["master", "collaborator"]
    joined_at: datetime


class CollabSyncConfig(BaseModel):
    """Sync settings shared across the team."""

    auto_sync: bool = True
    sync_interval_minutes: int = 60


class CollabManifest(BaseModel):
    """Root manifest stored as .collab.yaml."""

    version: str = "1"
    created_at: datetime
    members: list[CollabMember] = []
    sync: CollabSyncConfig = CollabSyncConfig()


def load_manifest(connection_path: Path) -> CollabManifest | None:
    """Load .collab.yaml from a connection directory.

    Returns None if the file does not exist.
    """
    manifest_path = connection_path / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path) as f:
            data = yaml.safe_load(f)
        if not data:
            return None
        return CollabManifest.model_validate(data)
    except Exception as e:
        logger.warning("Failed to load manifest: %s", e)
        return None


def save_manifest(connection_path: Path, manifest: CollabManifest) -> None:
    """Write .collab.yaml to the connection directory."""
    manifest_path = connection_path / MANIFEST_FILENAME
    data = manifest.model_dump(mode="json")
    with open(manifest_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_member(manifest: CollabManifest, user_id: str) -> CollabMember | None:
    """Find a member by user_id."""
    for member in manifest.members:
        if member.user_id == user_id:
            return member
    return None


def get_role(connection_path: Path, user_id: str) -> str | None:
    """Get role for a user_id, or None if not a member / no manifest."""
    manifest = load_manifest(connection_path)
    if manifest is None:
        return None
    member = get_member(manifest, user_id)
    return member.role if member else None


def get_user_name_from_config(config_file: Path) -> str | None:
    """Get user_name from global config.

    Args:
        config_file: Path to the YAML config file.
    """
    if not config_file.exists():
        return None
    with open(config_file) as f:
        config = yaml.safe_load(f) or {}
    return config.get("user_name")


def set_user_name_in_config(user_name: str, config_file: Path) -> None:
    """Set user_name in global config.

    Args:
        user_name: The user name to store.
        config_file: Path to the YAML config file.
    """
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    config["user_name"] = user_name
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def add_member(
    manifest: CollabManifest,
    user_name: str,
    user_id: str,
    role: Literal["master", "collaborator"] = "collaborator",
) -> CollabManifest:
    """Add a member to the manifest (returns updated manifest).

    If a member with the same user_id already exists, it is a no-op.
    """
    if get_member(manifest, user_id) is not None:
        return manifest
    member = CollabMember(
        user_name=user_name,
        user_id=user_id,
        role=role,
        joined_at=datetime.now(timezone.utc),
    )
    manifest.members.append(member)
    return manifest
