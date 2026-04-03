"""Example runtime factory for a community connector plugin."""

from pathlib import Path
from typing import Any

from db_mcp_data.connectors.api import (
    APIAuthConfig,
    APIConnector,
    APIConnectorConfig,
    APIEndpointConfig,
    APIPaginationConfig,
    APIQueryParamConfig,
)


def build_connector(
    connector_data: dict[str, Any],
    connection_path: Path,
    settings: Any,
) -> APIConnector:
    """Build a connector from the materialized connector.yaml payload.

    Real plugins can preprocess connector_data here before instantiating one of the
    shared core connector implementations, or return a fully custom connector.
    """
    auth_data = connector_data.get("auth", {}) or {}
    endpoints = []
    for endpoint_data in connector_data.get("endpoints", []) or []:
        if not isinstance(endpoint_data, dict):
            continue
        qp_data = endpoint_data.get("query_params", []) or []
        query_params = [
            APIQueryParamConfig(**query_param)
            for query_param in qp_data
            if isinstance(query_param, dict)
        ]
        endpoint_copy = dict(endpoint_data)
        endpoint_copy.pop("query_params", None)
        endpoints.append(APIEndpointConfig(**endpoint_copy, query_params=query_params))

    pagination_data = connector_data.get("pagination", {}) or {}

    config = APIConnectorConfig(
        profile=connector_data.get("profile", ""),
        base_url=connector_data.get("base_url", ""),
        template_id=connector_data.get("template_id", "example_widget"),
        auth=APIAuthConfig(**auth_data) if auth_data else APIAuthConfig(),
        endpoints=endpoints,
        pagination=APIPaginationConfig(**pagination_data)
        if pagination_data
        else APIPaginationConfig(),
        capabilities=connector_data.get("capabilities", {}) or {},
    )
    return APIConnector(
        config,
        data_dir=str(connection_path / "data"),
        env_path=str(connection_path / ".env"),
    )
