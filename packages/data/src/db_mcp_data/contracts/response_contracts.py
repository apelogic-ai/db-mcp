"""Backward-compatibility shim — canonical location is db_mcp_models.execution_contracts."""

from db_mcp_models.execution_contracts import (  # noqa: F401
    RESPONSE_CONTRACT_SCHEMA_VERSION,
    GetResultCompleteContract,
    GetResultErrorContract,
    GetResultRunningContract,
    RunSqlAsyncErrorContract,
    RunSqlAsyncSubmittedContract,
    RunSqlSyncSuccessContract,
    build_response_contract_schemas,
    get_response_contract_models,
)

__all__ = [
    "RESPONSE_CONTRACT_SCHEMA_VERSION",
    "GetResultCompleteContract",
    "GetResultErrorContract",
    "GetResultRunningContract",
    "RunSqlAsyncErrorContract",
    "RunSqlAsyncSubmittedContract",
    "RunSqlSyncSuccessContract",
    "build_response_contract_schemas",
    "get_response_contract_models",
]
