"""FastAPI server for db-mcp UI.

This module provides a FastAPI server that:
- Serves the BICP JSON-RPC endpoint for UI communication
- Provides WebSocket streaming for notifications
- Serves static files for the UI build
- Provides health checks
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Import the JSON-RPC request type from bicp_agent
from bicp_agent.types import JsonRpcRequest
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db_mcp.bicp import DBMCPAgent

logger = logging.getLogger(__name__)


def get_static_dir() -> Path:
    """Get the static files directory, handling PyInstaller bundles."""
    import sys

    if getattr(sys, "frozen", False):
        # Running from PyInstaller bundle
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        return base_path / "db_mcp" / "static"
    else:
        # Running from source
        return Path(__file__).parent / "static"


# Static files directory (UI build output)
STATIC_DIR = get_static_dir()


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | list[Any] | None = None
    id: str | int | None = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error."""

    code: int
    message: str
    data: Any | None = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    result: Any | None = None
    error: JSONRPCError | None = None
    id: str | int | None = None


# Global agent instance (initialized on startup)
_agent: DBMCPAgent | None = None

# Connected WebSocket clients for streaming notifications
_ws_clients: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _agent

    # Startup
    logger.info("Starting db-mcp UI server")
    _agent = DBMCPAgent()
    logger.info("BICP agent initialized")

    yield

    # Shutdown
    logger.info("Shutting down db-mcp UI server")
    _agent = None

    # Close all WebSocket connections
    for ws in list(_ws_clients):
        try:
            await ws.close()
        except Exception:
            pass
    _ws_clients.clear()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="db-mcp UI Server",
        description="FastAPI server for db-mcp UI with BICP support",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware for development (localhost:3000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        from importlib.metadata import version as pkg_version
        try:
            ver = pkg_version("db-mcp")
        except Exception:
            ver = "dev"
        return {
            "status": "healthy",
            "service": "db-mcp-ui",
            "version": ver,
        }

    @app.post("/api/spans")
    async def receive_spans(request: Request) -> JSONResponse:
        """Receive spans from the MCP server's HttpSpanExporter.

        Mirrors the console server's _receive_spans() so the UI server
        can be a drop-in replacement when DB_MCP_CONSOLE_PORT=8080.
        """
        from db_mcp.console.collector import Span, get_collector

        try:
            body = await request.body()
            data = json.loads(body.decode("utf-8"))

            collector = get_collector()
            spans_data = data.get("spans", [])
            for span_data in spans_data:
                span = Span(
                    trace_id=span_data["trace_id"],
                    span_id=span_data["span_id"],
                    parent_span_id=span_data.get("parent_span_id"),
                    name=span_data["name"],
                    start_time=span_data["start_time"],
                    end_time=span_data.get("end_time"),
                    status=span_data.get("status", "ok"),
                    attributes=span_data.get("attributes", {}),
                )
                collector.add_span(span)

            return JSONResponse(content={"status": "ok", "count": len(spans_data)})
        except Exception as e:
            logger.warning(f"Failed to receive spans: {e}")
            return JSONResponse(
                content={"status": "error", "error": str(e)},
                status_code=400,
            )

    @app.post("/bicp")
    async def bicp_handler(request: JSONRPCRequest) -> JSONResponse:
        """Handle BICP JSON-RPC requests.

        Routes requests to the DBMCPAgent handler.
        """
        if _agent is None:
            return JSONResponse(
                content=JSONRPCResponse(
                    error=JSONRPCError(
                        code=-32603,
                        message="Agent not initialized",
                    ),
                    id=request.id,
                ).model_dump(),
                status_code=500,
            )

        try:
            # Convert params to dict if it's a list
            params = request.params
            if isinstance(params, list):
                params = {"args": params}

            # Build the JSON-RPC request for the agent
            rpc_request = JsonRpcRequest(
                jsonrpc="2.0",
                id=request.id or 0,
                method=request.method,
                params=params,
            )

            # Route to agent handler
            response = await _agent.handle_request(rpc_request)

            # Return the response from the agent
            return JSONResponse(content=response.model_dump(exclude_none=True))

        except ValueError as e:
            # Invalid request
            return JSONResponse(
                content=JSONRPCResponse(
                    error=JSONRPCError(
                        code=-32602,
                        message=str(e),
                    ),
                    id=request.id,
                ).model_dump(),
                status_code=400,
            )

        except Exception as e:
            # Internal error
            logger.exception(f"BICP handler error: {e}")
            return JSONResponse(
                content=JSONRPCResponse(
                    error=JSONRPCError(
                        code=-32603,
                        message=f"Internal error: {e}",
                    ),
                    id=request.id,
                ).model_dump(),
                status_code=500,
            )

    @app.websocket("/bicp/stream")
    async def bicp_stream(websocket: WebSocket):
        """WebSocket endpoint for streaming BICP notifications.

        Clients connect here to receive:
        - query/progress: Query execution progress updates
        - query/result: Query result notifications
        """
        await websocket.accept()
        _ws_clients.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(_ws_clients)}")

        try:
            while True:
                # Keep connection alive, wait for messages from client
                # For v0.1, we mainly use this for server->client notifications
                data = await websocket.receive_text()
                logger.debug(f"WebSocket received: {data}")

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.warning(f"WebSocket error: {e}")
        finally:
            _ws_clients.discard(websocket)
            logger.info(f"WebSocket client removed. Total clients: {len(_ws_clients)}")

    # Serve index.html for root
    @app.get("/")
    async def serve_root():
        """Serve index.html for the root path."""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return JSONResponse(
            content={"message": "UI not built. Run UI build first."},
            status_code=404,
        )

    # Mount static files if directory exists
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


async def broadcast_notification(notification_type: str, data: dict[str, Any]) -> None:
    """Broadcast a notification to all connected WebSocket clients.

    Args:
        notification_type: Type of notification (e.g., "query/progress", "query/result")
        data: Notification payload
    """
    if not _ws_clients:
        return

    message = {
        "jsonrpc": "2.0",
        "method": notification_type,
        "params": data,
    }

    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
            disconnected.add(ws)

    # Clean up disconnected clients
    _ws_clients.difference_update(disconnected)


def start_ui_server(host: str = "0.0.0.0", port: int = 8080, log_file: Path | None = None) -> None:
    """Start the UI server.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to listen on (default: 8080)
        log_file: Path to log file (None for stdout)
    """
    import uvicorn

    # Configure logging
    log_config: dict | None = None
    if log_file:
        # Redirect all logs to file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            filename=str(log_file),
            filemode="a",
        )
        # Suppress uvicorn's default logging to console
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(log_file),
                    "formatter": "default",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["file"],
            },
        }
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    logger.info(f"Starting db-mcp UI server on {host}:{port}")
    uvicorn.run(
        "db_mcp.ui_server:create_app",
        host=host,
        port=port,
        factory=True,
        reload=False,
        workers=1,
        log_config=log_config,
    )


if __name__ == "__main__":
    start_ui_server()
