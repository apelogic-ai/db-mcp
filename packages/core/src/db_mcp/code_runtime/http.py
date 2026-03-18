"""HTTP surface for the shared db-mcp code runtime."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db_mcp.code_runtime import get_code_runtime_service
from db_mcp.code_runtime.interface import RUNTIME_INTERFACE_NATIVE, RuntimeInterface


class RuntimeRunRequest(BaseModel):
    """HTTP request body for code runtime execution."""

    connection: str
    code: str
    session_id: str | None = None
    timeout_seconds: int = 30
    confirmed: bool = False


class RuntimeSessionCreateRequest(BaseModel):
    """HTTP request body for session creation."""

    connection: str
    session_id: str | None = None
    interface: RuntimeInterface = RUNTIME_INTERFACE_NATIVE


class RuntimeSessionRunRequest(BaseModel):
    """HTTP request body for session-scoped code execution."""

    code: str
    timeout_seconds: int = 30
    confirmed: bool = False


class RuntimeSessionInvokeRequest(BaseModel):
    """HTTP request body for direct SDK method invocation."""

    args: list[object] = Field(default_factory=list)
    kwargs: dict[str, object] = Field(default_factory=dict)
    confirmed: bool = False


runtime_router = APIRouter()


@runtime_router.get("/api/runtime/contract")
async def runtime_contract(
    connection: str,
    session_id: str | None = None,
    interface: RuntimeInterface = RUNTIME_INTERFACE_NATIVE,
) -> JSONResponse:
    """Return the shared code runtime contract for one connection."""
    service = get_code_runtime_service()
    return JSONResponse(
        content=service.contract(connection, session_id=session_id, interface=interface)
    )


@runtime_router.post("/api/runtime/sessions")
async def runtime_create_session(request: RuntimeSessionCreateRequest) -> JSONResponse:
    """Create or resume a persistent host-managed runtime session."""
    service = get_code_runtime_service()
    session = service.create_session(request.connection, session_id=request.session_id)
    return JSONResponse(
        content=service.contract_for_session(session.session_id, interface=request.interface)
    )


@runtime_router.get("/api/runtime/sessions/{session_id}/contract")
async def runtime_session_contract(
    session_id: str,
    interface: RuntimeInterface = RUNTIME_INTERFACE_NATIVE,
) -> JSONResponse:
    """Return the runtime contract for an existing host-managed session."""
    service = get_code_runtime_service()
    return JSONResponse(content=service.contract_for_session(session_id, interface=interface))


@runtime_router.post("/api/runtime/sessions/{session_id}/run")
async def runtime_session_run(session_id: str, request: RuntimeSessionRunRequest) -> JSONResponse:
    """Execute Python code in an existing host-managed runtime session."""
    service = get_code_runtime_service()
    result = service.run_session(
        session_id,
        request.code,
        timeout_seconds=request.timeout_seconds,
        confirmed=request.confirmed,
    )
    return JSONResponse(content=result.to_dict())


@runtime_router.post("/api/runtime/sessions/{session_id}/sdk/{method}")
async def runtime_session_invoke(
    session_id: str,
    method: str,
    request: RuntimeSessionInvokeRequest,
) -> JSONResponse:
    """Invoke one host-runtime SDK method directly on the server."""
    service = get_code_runtime_service()
    result = service.invoke_session_method(
        session_id,
        method,
        args=request.args,
        kwargs=request.kwargs,
        confirmed=request.confirmed,
    )
    return JSONResponse(content=jsonable_encoder({"result": result}))


@runtime_router.delete("/api/runtime/sessions/{session_id}")
async def runtime_close_session(session_id: str) -> JSONResponse:
    """Close a host-managed runtime session."""
    service = get_code_runtime_service()
    closed = service.close_session(session_id)
    return JSONResponse(content={"session_id": session_id, "closed": closed})


@runtime_router.post("/api/runtime/run")
async def runtime_run(request: RuntimeRunRequest) -> JSONResponse:
    """Execute Python code via the shared runtime service."""
    service = get_code_runtime_service()
    if request.session_id and hasattr(service, "create_session"):
        service.create_session(request.connection, session_id=request.session_id)
    result = service.run(
        request.connection,
        request.code,
        session_id=request.session_id or "runtime-http",
        timeout_seconds=request.timeout_seconds,
        confirmed=request.confirmed,
    )
    return JSONResponse(content=result.to_dict())


def create_runtime_app() -> FastAPI:
    """Create a dedicated HTTP app for code-runtime access."""
    app = FastAPI(
        title="db-mcp Runtime Server",
        description="Persistent native runtime server for db-mcp code mode",
        version="0.1.0",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "db-mcp-runtime"}

    app.include_router(runtime_router)
    return app


def start_runtime_server(host: str = "127.0.0.1", port: int = 8091) -> None:
    """Start the dedicated runtime HTTP server."""
    import uvicorn

    uvicorn.run(
        create_runtime_app(),
        host=host,
        port=port,
        reload=False,
        workers=1,
        log_level="warning",
    )
