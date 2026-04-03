"""Tests for ConnectorAdapter protocol compliance."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from db_mcp_models.gateway import DataRequest, SQLQuery

from db_mcp_data.gateway.adapter import ConnectorAdapter


class _FullAdapter:
    """Minimal class that correctly satisfies ConnectorAdapter."""

    def can_handle(self, connector: Any) -> bool:
        return True

    def execute(
        self, connector: Any, request: DataRequest, *, connection_path: Path
    ) -> dict[str, Any]:
        return {}

    def introspect(
        self,
        connector: Any,
        scope: str,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str | None = None,
    ) -> dict[str, Any]:
        return {}


class _MissingExecute:
    def can_handle(self, connector: Any) -> bool:
        return True

    def introspect(self, connector: Any, scope: str, **kwargs: Any) -> dict[str, Any]:
        return {}


class _MissingIntrospect:
    def can_handle(self, connector: Any) -> bool:
        return True

    def execute(
        self, connector: Any, request: DataRequest, *, connection_path: Path
    ) -> dict[str, Any]:
        return {}


class _MissingCanHandle:
    def execute(
        self, connector: Any, request: DataRequest, *, connection_path: Path
    ) -> dict[str, Any]:
        return {}

    def introspect(self, connector: Any, scope: str, **kwargs: Any) -> dict[str, Any]:
        return {}


def test_full_adapter_satisfies_protocol():
    assert isinstance(_FullAdapter(), ConnectorAdapter)


def test_missing_execute_does_not_satisfy_protocol():
    assert not isinstance(_MissingExecute(), ConnectorAdapter)


def test_missing_introspect_does_not_satisfy_protocol():
    assert not isinstance(_MissingIntrospect(), ConnectorAdapter)


def test_missing_can_handle_does_not_satisfy_protocol():
    assert not isinstance(_MissingCanHandle(), ConnectorAdapter)


def test_execute_signature_accepts_expected_args():
    adapter = _FullAdapter()
    connector = MagicMock()
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
    result = adapter.execute(connector, request, connection_path=Path("/tmp"))
    assert isinstance(result, dict)


def test_introspect_signature_accepts_scope_and_kwargs():
    adapter = _FullAdapter()
    connector = MagicMock()
    result = adapter.introspect(connector, "tables", catalog="main", schema="public")
    assert isinstance(result, dict)


def test_valid_scopes_are_defined():
    from db_mcp_data.gateway.adapter import VALID_SCOPES
    assert VALID_SCOPES == {"catalogs", "schemas", "tables", "columns"}
