"""Tests for versioned connector.yaml contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from db_mcp.contracts.connector_contracts import (
    CONNECTOR_SPEC_VERSION,
    ConnectorContractV1,
    validate_connector_contract,
)


def test_validate_connector_contract_defaults_sql_profile():
    parsed = validate_connector_contract({"type": "sql", "database_url": "sqlite:////tmp/demo.db"})

    assert parsed.spec_version == CONNECTOR_SPEC_VERSION
    assert parsed.effective_profile == "sql_db"


def test_validate_connector_contract_rejects_unknown_major_version():
    with pytest.raises(ValidationError, match="major version"):
        validate_connector_contract(
            {
                "spec_version": "2.0.0",
                "type": "api",
                "profile": "api_openapi",
                "base_url": "https://api.example.com",
            }
        )


def test_validate_connector_contract_accepts_extension_profile():
    parsed = validate_connector_contract(
        {
            "spec_version": "1.1.0",
            "type": "api",
            "profile": "x-my-custom-profile",
            "base_url": "https://api.example.com",
        }
    )

    assert isinstance(parsed, ConnectorContractV1)
    assert parsed.profile == "x-my-custom-profile"


def test_validate_connector_contract_accepts_api_spec_url():
    parsed = validate_connector_contract(
        {
            "spec_version": "1.0.0",
            "type": "api",
            "profile": "api_openapi",
            "base_url": "https://api.example.com/v1",
            "spec_url": "https://cdn.example.com/openapi.json",
        }
    )

    assert isinstance(parsed, ConnectorContractV1)
    assert parsed.spec_url == "https://cdn.example.com/openapi.json"


def test_validate_connector_contract_rejects_profile_type_mismatch():
    with pytest.raises(ValidationError, match="not compatible"):
        validate_connector_contract(
            {
                "spec_version": "1.0.0",
                "type": "file",
                "profile": "api_openapi",
                "directory": "/tmp/files",
            }
        )


def test_validate_connector_contract_requires_file_source_or_directory():
    with pytest.raises(ValidationError, match="require either 'directory'"):
        validate_connector_contract({"spec_version": "1.0.0", "type": "file"})
