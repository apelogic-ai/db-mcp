"""Config dataclasses and builder for the API connector.

Extracted from ``api.py`` to reduce file size. All config types live here;
``api.py`` re-exports them for backward compatibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Any

# ---------------------------------------------------------------------------
# Auth value resolution
# ---------------------------------------------------------------------------

# Matches ${VAR_NAME} — the only syntax that triggers env var lookup.
_ENV_VAR_RE = re.compile(r"^\$\{([^}]+)\}$")


def _resolve_env_value(raw: str, env: dict[str, str]) -> str:
    """Resolve an auth config value: literal string or ``${VAR_NAME}`` env reference.

    Rules:
    - If *raw* matches ``${VAR_NAME}``, look up ``VAR_NAME`` in *env* and return
      its value (raises ``ValueError`` when the variable is missing).
    - Otherwise, return *raw* as-is — it is treated as a literal string.

    Examples::

        _resolve_env_value("admin", env)              # → "admin"  (literal)
        _resolve_env_value("${API_PASSWORD}", env)  # → env["API_PASSWORD"]
    """
    if not raw:
        return ""
    m = _ENV_VAR_RE.match(raw)
    if m:
        var_name = m.group(1)
        if var_name not in env:
            raise ValueError(
                f"Auth env var '{var_name}' not found in .env file. "
                f"Add {var_name}=<value> to your .env file."
            )
        return env[var_name]
    return raw  # literal — use as-is


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class APIQueryParamConfig:
    """Metadata for a query parameter accepted by an API endpoint."""

    name: str
    type: str = "string"  # string, integer, number, boolean
    description: str = ""
    required: bool = False
    enum: list[str] | None = None
    default: str | None = None


@dataclass
class APIEndpointConfig:
    """A single API endpoint (maps to one table)."""

    name: str
    path: str
    description: str = ""
    method: str = "GET"
    query_params: list[APIQueryParamConfig] = field(default_factory=list)
    body_mode: str = "query"  # query | json
    body_template: dict[str, Any] | None = None
    response_mode: str = "data"  # data | raw
    sql_field: str = "sql"  # Field name for SQL in execute_sql endpoints


@dataclass
class APIPaginationConfig:
    """Pagination strategy for API requests."""

    type: str = "none"  # cursor | offset | link_header | none
    cursor_param: str = "starting_after"
    cursor_field: str = "data[-1].id"
    offset_param: str = "offset"
    page_size_param: str = "limit"
    page_size: int = 100
    data_field: str = "data"  # JSON path to array of results


@dataclass
class APIAuthConfig:
    """Authentication configuration."""

    type: str = "bearer"  # none | bearer | header | query_param | basic | login | jwt_login
    token_env: str = ""  # env var name for the token (always resolved as env var name)
    header_name: str = "Authorization"
    token_prefix: str = "Bearer "
    param_name: str = "api_key"
    # jwt_login fields (canonical names)
    login_endpoint: str = ""
    username_env: str = ""  # explicit env var name for username (always resolved as env var name)
    password_env: str = ""  # explicit env var name for password (always resolved as env var name)
    token_field: str = "access_token"
    # Alias / convenience fields — accepted from connector.yaml.
    # __post_init__ normalizes login_url → login_endpoint.
    # username / password support BOTH literal values and ${VAR_NAME} references:
    #   username: admin            → literal "admin"
    #   username: ${MY_USER_ENV}   → resolved from .env at login time
    # If the value matches ${VAR_NAME}, __post_init__ extracts the var name into
    # username_env / password_env so the canonical lookup path is used.
    login_url: str | None = None  # alias for login_endpoint
    username: str | None = None  # literal value OR ${VAR_NAME} reference
    password: str | None = None  # literal value OR ${VAR_NAME} reference
    login_body: dict[str, Any] | None = None  # Extra fields merged into JWT login payload
    # bearer / header token convenience alias — same literal-or-${VAR} semantics.
    token: str | None = None  # alias for token_env; supports literal or ${VAR_NAME}
    refresh: str | None = None  # reserved: refresh-token endpoint path

    def __post_init__(self) -> None:
        """Normalize alias fields.

        - ``login_url`` is always copied to ``login_endpoint`` (it is a URL, never
          an env var reference).
        - ``username`` / ``password`` / ``token``: if the value matches ``${VAR}``,
          extract the var name into the canonical ``*_env`` field so the existing
          env-lookup path is used.  If the value is a plain string (literal), leave
          the ``*_env`` field empty — ``_jwt_login`` / ``_resolve_auth_headers`` will
          fall back to the alias field directly.
        - Canonical fields (``username_env``, ``password_env``, ``token_env``) always
          win; alias fields never override them.
        """
        if self.login_url is not None and not self.login_endpoint:
            self.login_endpoint = self.login_url

        for alias_attr, env_attr in (
            ("username", "username_env"),
            ("password", "password_env"),
            ("token", "token_env"),
        ):
            alias_val = getattr(self, alias_attr)
            if alias_val is not None and not getattr(self, env_attr):
                m = _ENV_VAR_RE.match(alias_val)
                if m:
                    # ${VAR_NAME} → extract and store as env var name
                    setattr(self, env_attr, m.group(1))
                # else: plain literal — leave *_env empty, use alias field directly


@dataclass
class APIConnectorConfig:
    """Configuration for the API connector."""

    type: str = field(default="api", init=False)
    profile: str = ""
    base_url: str = ""
    spec_url: str = ""
    template_id: str = ""
    auth: APIAuthConfig = field(default_factory=APIAuthConfig)
    endpoints: list[APIEndpointConfig] = field(default_factory=list)
    pagination: APIPaginationConfig = field(default_factory=APIPaginationConfig)
    rate_limit_rps: float = 10.0
    capabilities: dict[str, Any] = field(default_factory=dict)
    api_title: str = ""  # Display name from discovery
    api_description: str = ""  # Description from API spec


def _filter_dataclass_kwargs(cls: type[Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only supported init kwargs for a dataclass."""
    valid_fields = {f.name for f in fields(cls) if f.init}
    return {key: value for key, value in raw.items() if key in valid_fields}


def build_api_connector_config(data: dict[str, Any]) -> APIConnectorConfig:
    """Build ``APIConnectorConfig`` from a connector payload."""
    auth_data = data.get("auth", {})
    auth = (
        APIAuthConfig(**_filter_dataclass_kwargs(APIAuthConfig, auth_data))
        if auth_data
        else APIAuthConfig()
    )

    endpoints_data = data.get("endpoints", [])
    endpoints = []
    for endpoint_entry in endpoints_data:
        endpoint_data = _filter_dataclass_kwargs(APIEndpointConfig, dict(endpoint_entry))
        qp_data = endpoint_data.pop("query_params", [])
        query_params = [
            APIQueryParamConfig(**_filter_dataclass_kwargs(APIQueryParamConfig, qp))
            for qp in qp_data
        ]
        method = str(endpoint_data.get("method", "GET")).upper()
        if "body_mode" not in endpoint_data and method != "GET":
            endpoint_data["body_mode"] = "json"
        endpoints.append(APIEndpointConfig(**endpoint_data, query_params=query_params))

    pagination_data = data.get("pagination", {})
    pagination = (
        APIPaginationConfig(**_filter_dataclass_kwargs(APIPaginationConfig, pagination_data))
        if pagination_data
        else APIPaginationConfig()
    )

    rate_limit = data.get("rate_limit", {})
    rate_limit_rps = rate_limit.get("requests_per_second", 10.0) if rate_limit else 10.0

    return APIConnectorConfig(
        profile=data.get("profile", ""),
        base_url=data.get("base_url", ""),
        spec_url=data.get("spec_url", ""),
        template_id=data.get("template_id", ""),
        auth=auth,
        endpoints=endpoints,
        pagination=pagination,
        rate_limit_rps=rate_limit_rps,
        capabilities=data.get("capabilities", {}) or {},
        api_title=data.get("api_title", ""),
        api_description=data.get("api_description", ""),
    )
