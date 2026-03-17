"""Shared Python-native code runtime for db-mcp."""

from db_mcp.code_runtime.backend import CodeResult, CodeSession, create_code_session, run_code
from db_mcp.code_runtime.client import CodeRuntimeClient, CodeRuntimeSessionClient
from db_mcp.code_runtime.contract import (
    HELPER_METHODS,
    build_code_mode_contract,
    build_code_mode_instructions,
)
from db_mcp.code_runtime.host import (
    CodeModeHost,
)
from db_mcp.code_runtime.interface import (
    RUNTIME_INTERFACE_CLI,
    RUNTIME_INTERFACE_MCP,
    RUNTIME_INTERFACE_NATIVE,
    RuntimeInterface,
    build_runtime_contract,
    build_runtime_instructions,
)
from db_mcp.code_runtime.native_adapter import (
    CodeRuntimeNativeAdapter,
    NativeRuntimeMaterialization,
)
from db_mcp.code_runtime.runtime import CodeModeRuntime
from db_mcp.code_runtime.service import (
    CodeRuntimeHostSession,
    CodeRuntimeService,
    get_code_runtime_service,
)

__all__ = [
    "HELPER_METHODS",
    "RuntimeInterface",
    "RUNTIME_INTERFACE_CLI",
    "RUNTIME_INTERFACE_MCP",
    "RUNTIME_INTERFACE_NATIVE",
    "build_code_mode_contract",
    "build_code_mode_instructions",
    "build_runtime_contract",
    "build_runtime_instructions",
    "CodeRuntimeNativeAdapter",
    "NativeRuntimeMaterialization",
    "CodeModeHost",
    "CodeRuntimeClient",
    "CodeRuntimeHostSession",
    "CodeRuntimeSessionClient",
    "CodeModeRuntime",
    "CodeRuntimeService",
    "CodeResult",
    "CodeSession",
    "create_code_session",
    "get_code_runtime_service",
    "run_code",
]
