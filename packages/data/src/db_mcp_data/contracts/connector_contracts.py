"""Backward-compatibility shim — canonical location is db_mcp_models.connector."""

from db_mcp_models.connector import (  # noqa: F401
    CONNECTOR_CONTRACT_SCHEMA_VERSION,
    CONNECTOR_SPEC_VERSION,
    CatalogMetadataContract,
    ConnectorContractV1,
    FileSourceContract,
    build_connector_contract_schemas,
    format_validation_error,
    get_connector_contract_models,
    validate_connector_contract,
)

__all__ = [
    "CONNECTOR_CONTRACT_SCHEMA_VERSION",
    "CONNECTOR_SPEC_VERSION",
    "CatalogMetadataContract",
    "ConnectorContractV1",
    "FileSourceContract",
    "build_connector_contract_schemas",
    "format_validation_error",
    "get_connector_contract_models",
    "validate_connector_contract",
]
