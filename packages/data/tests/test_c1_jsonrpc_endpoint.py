"""TDD tests for C1 — JSON-RPC body_mode support in APIConnector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 1. APIEndpointConfig accepts body_mode='jsonrpc' and rpc_method
# ---------------------------------------------------------------------------


def test_endpoint_config_accepts_jsonrpc_body_mode():
    """APIEndpointConfig must accept body_mode='jsonrpc'."""
    from db_mcp_data.connectors.api_config import APIEndpointConfig

    ep = APIEndpointConfig(
        name="get_ledger",
        path="/rpc",
        method="POST",
        body_mode="jsonrpc",
        rpc_method="getLedger",
    )
    assert ep.body_mode == "jsonrpc"
    assert ep.rpc_method == "getLedger"


def test_endpoint_config_rpc_method_defaults_to_empty():
    """rpc_method defaults to empty string when not provided."""
    from db_mcp_data.connectors.api_config import APIEndpointConfig

    ep = APIEndpointConfig(name="do_something", path="/rpc")
    assert ep.rpc_method == ""


# ---------------------------------------------------------------------------
# 2. _send_non_get wraps params in JSON-RPC envelope for body_mode='jsonrpc'
# ---------------------------------------------------------------------------


def _make_connector(tmp_path):
    from db_mcp_data.connectors.api import APIConnector
    from db_mcp_data.connectors.api_config import APIConnectorConfig, APIEndpointConfig

    config = APIConnectorConfig(
        base_url="https://rpc.example.com",
        endpoints=[
            APIEndpointConfig(
                name="get_ledger",
                path="/rpc",
                method="POST",
                body_mode="jsonrpc",
                rpc_method="getLedger",
            )
        ],
    )
    return APIConnector(config, data_dir=str(tmp_path))


def test_send_non_get_jsonrpc_posts_correct_envelope(tmp_path):
    """_send_non_get with body_mode='jsonrpc' must POST a JSON-RPC 2.0 envelope."""
    from db_mcp_data.connectors.api_config import APIEndpointConfig

    connector = _make_connector(tmp_path)
    endpoint = APIEndpointConfig(
        name="get_ledger",
        path="/rpc",
        method="POST",
        body_mode="jsonrpc",
        rpc_method="getLedger",
    )

    captured_body: list = []

    def fake_post(url, headers, json, params, timeout):
        captured_body.append(json)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": [{"slot": 12345}]}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    with patch("requests.post", side_effect=fake_post):
        connector._send_non_get(
            "https://rpc.example.com/rpc",
            {},
            {"slot": "12345"},
            endpoint,
        )

    assert len(captured_body) == 1
    body = captured_body[0]
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "getLedger"
    assert body["params"] == {"slot": "12345"}
    assert "id" in body


def test_send_non_get_jsonrpc_returns_result_field(tmp_path):
    """_send_non_get with body_mode='jsonrpc' must return response['result']."""
    from db_mcp_data.connectors.api_config import APIEndpointConfig

    connector = _make_connector(tmp_path)
    endpoint = APIEndpointConfig(
        name="get_ledger",
        path="/rpc",
        method="POST",
        body_mode="jsonrpc",
        rpc_method="getLedger",
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": [{"slot": 12345, "hash": "abc"}],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp):
        result = connector._send_non_get(
            "https://rpc.example.com/rpc",
            {},
            {"slot": "12345"},
            endpoint,
        )

    assert result == [{"slot": 12345, "hash": "abc"}]


def test_send_non_get_jsonrpc_raises_on_error_field(tmp_path):
    """_send_non_get with body_mode='jsonrpc' must raise if response contains 'error'."""
    from db_mcp_data.connectors.api_config import APIEndpointConfig

    connector = _make_connector(tmp_path)
    endpoint = APIEndpointConfig(
        name="get_ledger",
        path="/rpc",
        method="POST",
        body_mode="jsonrpc",
        rpc_method="getLedger",
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32600, "message": "Invalid request"},
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp):
        try:
            connector._send_non_get(
                "https://rpc.example.com/rpc",
                {},
                {},
                endpoint,
            )
            raised = False
        except Exception:
            raised = True

    assert raised, "_send_non_get must raise when JSON-RPC response contains 'error'"


# ---------------------------------------------------------------------------
# 3. query_endpoint end-to-end with body_mode='jsonrpc'
# ---------------------------------------------------------------------------


def test_query_endpoint_jsonrpc_returns_rows(tmp_path):
    """query_endpoint with body_mode='jsonrpc' endpoint returns rows from 'result'."""
    from db_mcp_data.connectors.api import APIConnector
    from db_mcp_data.connectors.api_config import (
        APIConnectorConfig,
        APIEndpointConfig,
        APIQueryParamConfig,
    )

    config = APIConnectorConfig(
        base_url="https://rpc.example.com",
        endpoints=[
            APIEndpointConfig(
                name="get_ledger",
                path="/rpc",
                method="POST",
                body_mode="jsonrpc",
                rpc_method="getLedger",
                query_params=[APIQueryParamConfig(name="slot", type="integer")],
            )
        ],
    )
    connector = APIConnector(config, data_dir=str(tmp_path))

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": [{"slot": 12345, "leader": "Alice"}],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp):
        result = connector.query_endpoint("get_ledger", {"slot": "12345"})

    assert result["rows_returned"] == 1
    assert result["data"] == [{"slot": 12345, "leader": "Alice"}]


# ---------------------------------------------------------------------------
# 4. YAML round-trip: body_mode=jsonrpc survives build_api_connector_config
# ---------------------------------------------------------------------------


def test_build_api_connector_config_parses_jsonrpc_body_mode():
    """build_api_connector_config must parse body_mode=jsonrpc and rpc_method from YAML."""
    from db_mcp_data.connectors.api_config import build_api_connector_config

    raw = {
        "base_url": "https://rpc.example.com",
        "endpoints": [
            {
                "name": "get_ledger",
                "path": "/rpc",
                "method": "POST",
                "body_mode": "jsonrpc",
                "rpc_method": "getLedger",
            }
        ],
    }
    config = build_api_connector_config(raw)
    ep = config.endpoints[0]
    assert ep.body_mode == "jsonrpc"
    assert ep.rpc_method == "getLedger"
