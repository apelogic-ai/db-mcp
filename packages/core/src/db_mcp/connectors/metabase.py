"""Metabase connector — SQL-like connector via Metabase API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from db_mcp.db.connection import DatabaseError

# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MetabaseAuthConfig:
    """Authentication configuration for Metabase session auth."""

    type: str = "session"
    username_env: str = "MB_USERNAME"
    password_env: str = "MB_PASSWORD"


@dataclass
class MetabaseConnectorConfig:
    """Configuration for Metabase connector."""

    type: str = field(default="metabase", init=False)
    base_url: str = ""
    database_id: int | None = None
    database_name: str | None = None
    auth: MetabaseAuthConfig = field(default_factory=MetabaseAuthConfig)
    capabilities: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class MetabaseConnector:
    """Connector for Metabase using the SQL-like API surface."""

    def __init__(
        self,
        config: MetabaseConnectorConfig,
        env_path: str | None = None,
    ) -> None:
        self.config = config
        self._env_path = env_path
        self._session_token: str | None = None
        self._schema_cache: list[dict[str, Any]] | None = None

    # -- Auth ---------------------------------------------------------------

    def _load_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        if self._env_path:
            env_path = self._env_path
        else:
            env_path = None

        if env_path:
            from pathlib import Path

            path = Path(env_path)
            if path.exists():
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
        return env

    def _resolve_credentials(self) -> tuple[str, str]:
        env = self._load_env()
        username_key = self.config.auth.username_env
        password_key = self.config.auth.password_env

        if username_key not in env:
            raise ValueError(
                f"Auth username env var '{username_key}' not found in .env file. "
                f"Add {username_key}=<your-username> to your .env file."
            )
        if password_key not in env:
            raise ValueError(
                f"Auth password env var '{password_key}' not found in .env file. "
                f"Add {password_key}=<your-password> to your .env file."
            )

        return env[username_key], env[password_key]

    def _get_session_token(self) -> str:
        if self._session_token:
            return self._session_token

        username, password = self._resolve_credentials()
        url = self.config.base_url.rstrip("/") + "/api/session"
        resp = requests.post(url, json={"username": username, "password": password}, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        token = body.get("id") or body.get("session_id")
        if not token:
            raise ValueError("Metabase session token not found in response")
        self._session_token = token
        return token

    def _session_headers(self) -> dict[str, str]:
        token = self._get_session_token()
        return {"X-Metabase-Session": token}

    # -- Helpers ------------------------------------------------------------

    def _require_database_id(self) -> int:
        if self.config.database_id is None:
            raise ValueError("Metabase database_id is required")
        return self.config.database_id

    def _fetch_schema(self) -> list[dict[str, Any]]:
        if self._schema_cache is not None:
            return self._schema_cache

        db_id = self._require_database_id()
        url = self.config.base_url.rstrip("/") + f"/api/database/{db_id}/schema"
        resp = requests.get(url, headers=self._session_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected schema response from Metabase")
        self._schema_cache = data
        return data

    @staticmethod
    def _map_type(base_type: str | None) -> str:
        if not base_type:
            return "VARCHAR"
        base_type = base_type.lower()
        if "integer" in base_type:
            return "INTEGER"
        if "float" in base_type or "number" in base_type or "decimal" in base_type:
            return "DOUBLE"
        if "boolean" in base_type:
            return "BOOLEAN"
        if "datetime" in base_type or "date" in base_type:
            return "TIMESTAMP"
        return "VARCHAR"

    # -- Protocol methods ---------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        if not self.config.base_url:
            return {
                "connected": False,
                "dialect": "metabase",
                "error": "No base_url configured",
            }
        try:
            url = self.config.base_url.rstrip("/") + "/api/user/current"
            resp = requests.get(url, headers=self._session_headers(), timeout=10)
            resp.raise_for_status()
            return {"connected": True, "dialect": "metabase", "error": None}
        except Exception as exc:
            return {"connected": False, "dialect": "metabase", "error": str(exc)}

    def get_dialect(self) -> str:
        return "metabase"

    def get_catalogs(self) -> list[str | None]:
        if self.config.database_name:
            return [self.config.database_name]
        if self.config.database_id is not None:
            return [str(self.config.database_id)]
        return [None]

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        schemas = {t.get("schema") for t in self._fetch_schema() if t.get("schema")}
        return sorted(schemas) if schemas else [None]

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for t in self._fetch_schema():
            t_schema = t.get("schema")
            if schema and t_schema != schema:
                continue
            name = t.get("name")
            if not name:
                continue
            full_name = f"{t_schema}.{name}" if t_schema else name
            tables.append(
                {
                    "name": name,
                    "schema": t_schema,
                    "catalog": self.get_catalogs()[0],
                    "type": "table",
                    "full_name": full_name,
                }
            )
        return tables

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        for t in self._fetch_schema():
            if t.get("name") != table_name:
                continue
            if schema and t.get("schema") != schema:
                continue
            fields = t.get("fields", []) or []
            return [
                {
                    "name": f.get("name"),
                    "type": self._map_type(f.get("base_type")),
                    "nullable": True,
                    "default": None,
                    "primary_key": False,
                    "comment": None,
                }
                for f in fields
                if f.get("name")
            ]
        raise DatabaseError(f"Table not found: {table_name}")

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if schema:
            sql = f"SELECT * FROM {schema}.{table_name} LIMIT {limit}"
        else:
            sql = f"SELECT * FROM {table_name} LIMIT {limit}"
        return self.execute_sql(sql)

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        try:
            db_id = self._require_database_id()
            url = self.config.base_url.rstrip("/") + "/api/dataset"
            payload = {
                "database": db_id,
                "type": "native",
                "native": {"query": sql},
            }
            resp = requests.post(url, headers=self._session_headers(), json=payload, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {})
            cols = data.get("cols", [])
            rows = data.get("rows", [])
            names = [c.get("name") for c in cols]
            return [dict(zip(names, row)) for row in rows]
        except Exception as exc:
            raise DatabaseError(f"Failed to execute SQL via Metabase: {exc}") from exc
