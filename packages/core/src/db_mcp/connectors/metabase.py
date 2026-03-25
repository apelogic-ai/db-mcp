"""Backward-compatible Metabase connector built on the generic API connector."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from db_mcp.connectors.api import (
    APIAuthConfig,
    APIConnector,
    APIConnectorConfig,
    APIEndpointConfig,
)


@dataclass
class MetabaseAuthConfig:
    """Authentication configuration for Metabase."""

    type: str = "session"  # session | api_key
    username_env: str = "MB_USERNAME"
    password_env: str = "MB_PASSWORD"
    key_env: str = "MB_API_KEY"


@dataclass
class MetabaseConnectorConfig:
    """Configuration for the backward-compatible Metabase connector."""

    type: str = field(default="metabase", init=False)
    profile: str = ""
    base_url: str = ""
    database_id: int | None = None
    database_name: str | None = None
    auth: MetabaseAuthConfig = field(default_factory=MetabaseAuthConfig)
    capabilities: dict[str, Any] = field(default_factory=dict)


class MetabaseConnector:
    """Compatibility wrapper that delegates auth and SQL execution to APIConnector."""

    def __init__(
        self,
        config: MetabaseConnectorConfig,
        env_path: str | None = None,
    ) -> None:
        self.config = config
        self._env_path = env_path
        self._schema_cache: list[dict[str, Any]] | None = None

        env_file = Path(env_path) if env_path else None
        data_dir = str((env_file.parent if env_file else Path.cwd()) / "data")
        self._api = APIConnector(self._build_api_config(), data_dir=data_dir, env_path=env_path)

    def _build_api_config(self) -> APIConnectorConfig:
        endpoints = [
            APIEndpointConfig(
                name="execute_sql",
                path="/api/dataset",
                method="POST",
                body_mode="json",
            )
        ]
        if self.config.database_id is not None:
            endpoints[0].body_template = {
                "database": self.config.database_id,
                "type": "native",
                "native": {"query": "{{sql}}"},
            }

        capabilities = {
            "supports_sql": True,
            "supports_validate_sql": False,
            "supports_async_jobs": False,
            "sql_mode": "api_sync",
            "supports_endpoint_discovery": True,
            "supports_dashboard_api": True,
        }
        capabilities.update(self.config.capabilities)

        return APIConnectorConfig(
            profile=self.config.profile or "hybrid_bi",
            base_url=self.config.base_url,
            auth=self._build_api_auth_config(),
            endpoints=endpoints,
            capabilities=capabilities,
            api_title="Metabase",
        )

    def _build_api_auth_config(self) -> APIAuthConfig:
        if self.config.auth.type == "api_key":
            return APIAuthConfig(
                type="header",
                token_env=self.config.auth.key_env,
                header_name="x-api-key",
            )

        return APIAuthConfig(
            type="login",
            login_endpoint="/api/session",
            username_env=self.config.auth.username_env,
            password_env=self.config.auth.password_env,
            token_field="id",
            header_name="X-Metabase-Session",
            token_prefix="",
        )

    def _load_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        if not self._env_path:
            return env

        path = Path(self._env_path)
        if not path.exists():
            return env

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

    def _auth_headers(self) -> dict[str, str]:
        return self._api._resolve_auth_headers()

    def _require_database_id(self) -> int:
        if self.config.database_id is None:
            raise ValueError("Metabase database_id is required")
        return self.config.database_id

    def _fetch_schema(self) -> list[dict[str, Any]]:
        if self._schema_cache is not None:
            return self._schema_cache

        db_id = self._require_database_id()
        url = self.config.base_url.rstrip("/") + f"/api/database/{db_id}/schema"
        resp = requests.get(url, headers=self._auth_headers(), timeout=30)
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

    def test_connection(self) -> dict[str, Any]:
        if not self.config.base_url:
            return {
                "connected": False,
                "dialect": "metabase",
                "error": "No base_url configured",
            }
        try:
            url = self.config.base_url.rstrip("/") + "/api/user/current"
            resp = requests.get(url, headers=self._auth_headers(), timeout=10)
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
        schemas = {table.get("schema") for table in self._fetch_schema() if table.get("schema")}
        return sorted(schemas) if schemas else [None]

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for table in self._fetch_schema():
            table_schema = table.get("schema")
            if schema and table_schema != schema:
                continue
            name = table.get("name")
            if not name:
                continue
            full_name = f"{table_schema}.{name}" if table_schema else name
            tables.append(
                {
                    "name": name,
                    "schema": table_schema,
                    "catalog": self.get_catalogs()[0],
                    "type": "table",
                    "full_name": full_name,
                }
            )
        return tables

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        for table in self._fetch_schema():
            if table.get("name") != table_name:
                continue
            if schema and table.get("schema") != schema:
                continue
            fields = table.get("fields", []) or []
            return [
                {
                    "name": field.get("name"),
                    "type": self._map_type(field.get("base_type")),
                    "nullable": True,
                    "default": None,
                    "primary_key": False,
                    "comment": None,
                }
                for field in fields
                if field.get("name")
            ]
        raise ValueError(f"Table not found: {table_name}")

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        source = f"{schema}.{table_name}" if schema else table_name
        return self.execute_sql(f"SELECT * FROM {source} LIMIT {limit}")

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        self._require_database_id()
        return self._api.execute_sql(sql, params)
