"""Authentication helpers for the API connector.

Extracted from ``APIConnector`` to reduce the size of ``api.py``.
All functions receive explicit state rather than ``self``.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from db_mcp_data.connectors.api import APIAuthConfig, APIConnectorConfig


def load_env(env_path: str | None, data_dir: Path) -> dict[str, str]:
    """Load environment variables from .env file."""
    if env_path:
        p = Path(env_path)
    else:
        p = data_dir.parent / ".env"

    env: dict[str, str] = {}
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip("\"'")
    return env


def resolve_auth_headers(
    api_config: APIConnectorConfig,
    env_path: str | None,
    data_dir: Path,
    jwt_token: str | None,
    jwt_login_fn: Any,
) -> dict[str, str]:
    """Build auth headers from config + .env.

    ``jwt_login_fn`` is called (no args) when a JWT token is needed but missing.
    It should populate the connector's ``_jwt_token`` and return the new token.
    """
    auth_type = api_config.auth.type

    if auth_type == "none":
        return {}

    if auth_type in {"jwt_login", "login"}:
        token = jwt_token
        if token is None:
            token = jwt_login_fn()
        token_prefix = api_config.auth.token_prefix
        full_token = f"{token_prefix}{token}" if token_prefix else token
        return {api_config.auth.header_name: full_token}

    if auth_type == "basic":
        username, password = resolve_basic_credentials(api_config.auth, env_path, data_dir)
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    env = load_env(env_path, data_dir)
    auth = api_config.auth
    token_env = auth.token_env

    if token_env:
        if token_env not in env:
            raise ValueError(
                f"Auth token env var '{token_env}' not found in .env file. "
                f"Add {token_env}=<your-token> to your .env file."
            )
        token = env[token_env]
    else:
        token = auth.token or ""

    if auth_type == "bearer":
        return {"Authorization": f"Bearer {token}"}
    elif auth_type == "header":
        return {auth.header_name: token}
    elif auth_type == "query_param":
        return {}
    else:
        return {}


def resolve_basic_credentials(
    auth: APIAuthConfig, env_path: str | None, data_dir: Path
) -> tuple[str, str]:
    """Resolve username/password for basic auth from env or literal aliases."""
    env = load_env(env_path, data_dir)

    if auth.username_env:
        if auth.username_env not in env:
            raise ValueError(
                f"Basic auth username env var '{auth.username_env}' not found in .env file. "
                f"Add {auth.username_env}=<username> to your .env file."
            )
        username = env[auth.username_env]
    else:
        username = auth.username or ""

    if auth.password_env:
        if auth.password_env not in env:
            raise ValueError(
                f"Basic auth password env var '{auth.password_env}' not found in .env file. "
                f"Add {auth.password_env}=<password> to your .env file."
            )
        password = env[auth.password_env]
    else:
        password = auth.password or ""

    if not username:
        raise ValueError("Basic auth requires a username or username_env")
    if not password:
        raise ValueError("Basic auth requires a password or password_env")

    return username, password


def jwt_login(
    api_config: APIConnectorConfig,
    env_path: str | None,
    data_dir: Path,
) -> tuple[str, float]:
    """Perform JWT login: POST creds to login endpoint.

    Returns ``(token, expires_at)`` tuple.
    """
    auth = api_config.auth
    env = load_env(env_path, data_dir)

    # -- resolve username --
    if auth.username_env:
        if auth.username_env not in env:
            raise ValueError(
                f"JWT username env var '{auth.username_env}' not found in .env file. "
                f"Add {auth.username_env}=<username> to your .env file."
            )
        username = env[auth.username_env]
    else:
        username = auth.username or ""

    # -- resolve password --
    if auth.password_env:
        if auth.password_env not in env:
            raise ValueError(
                f"JWT password env var '{auth.password_env}' not found in .env file. "
                f"Add {auth.password_env}=<password> to your .env file."
            )
        password = env[auth.password_env]
    else:
        password = auth.password or ""

    login_url = api_config.base_url.rstrip("/") + auth.login_endpoint
    payload: dict[str, Any] = {"username": username, "password": password}
    if auth.login_body:
        payload.update(auth.login_body)
        payload["username"] = username
        payload["password"] = password
    resp = requests.post(login_url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    token_field = auth.token_field or "access_token"
    token = data.get(token_field)
    if not token:
        raise ValueError(
            f"JWT login response missing token field '{token_field}'. "
            f"Response keys: {list(data.keys())}"
        )
    expires_at = time.time() + 3600  # Default 1h cache
    return token, expires_at


def resolve_auth_params(
    api_config: APIConnectorConfig,
    env_path: str | None,
    data_dir: Path,
) -> dict[str, str]:
    """Build auth query params (for query_param auth type)."""
    if api_config.auth.type != "query_param":
        return {}
    auth = api_config.auth
    env = load_env(env_path, data_dir)
    if auth.token_env:
        token = env.get(auth.token_env, "")
    else:
        token = auth.token or ""
    return {auth.param_name: token}
