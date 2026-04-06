"""FastAPI server for db-mcp UI.

This module provides a FastAPI server that:
- Serves the REST API for UI communication (/api/*)
- Serves static files for the UI build
- Provides health checks
"""

import json
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from db_mcp.api.router import router as api_router
from db_mcp.code_runtime.http import runtime_router

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compute_ui_source_hash(ui_dir: Path) -> str:
    targets = [
        ui_dir / "src",
        ui_dir / "public",
        ui_dir / "next.config.js",
        ui_dir / "package.json",
        ui_dir / "postcss.config.js",
        ui_dir / "tailwind.config.js",
        ui_dir / "tsconfig.json",
    ]
    digest = sha256()
    for target in targets:
        if target.is_dir():
            paths = sorted(path for path in target.rglob("*") if path.is_file())
        elif target.is_file():
            paths = [target]
        else:
            continue

        for path in paths:
            relative = path.relative_to(ui_dir)
            digest.update(str(relative).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def validate_static_bundle_provenance() -> None:
    """Fail fast when source-mode UI server would serve stale staged assets."""
    import sys

    if getattr(sys, "frozen", False):
        return
    if STATIC_DIR.exists() is False:
        raise RuntimeError(
            "Static UI bundle missing. Run ./scripts/stage_ui_static.sh --build before db-mcp ui."
        )
    if (STATIC_DIR / ".build-info.json").exists() is False:
        raise RuntimeError(
            "Static UI provenance missing. "
            "Re-stage the UI with ./scripts/stage_ui_static.sh --build."
        )
    if os.environ.get("DB_MCP_UI_SKIP_STATIC_CHECK", "").strip() == "1":
        logger.warning("Skipping static UI provenance check because DB_MCP_UI_SKIP_STATIC_CHECK=1")
        return

    build_info = json.loads((STATIC_DIR / ".build-info.json").read_text())
    repo_root = _repo_root()
    ui_dir = repo_root / "packages" / "ui"
    current_source_hash = _compute_ui_source_hash(ui_dir)
    current_git_sha = "unknown"
    try:
        current_git_sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        pass

    if build_info.get("uiSourceHash") != current_source_hash:
        raise RuntimeError(
            "Static UI bundle is stale for the current packages/ui sources. "
            "Run ./scripts/stage_ui_static.sh --build before starting db-mcp ui."
        )

    built_sha = build_info.get("gitSha")
    sha_mismatch = (
        built_sha
        and built_sha != "unknown"
        and current_git_sha != "unknown"
        and built_sha != current_git_sha
    )
    if sha_mismatch:
        logger.warning(
            "Static UI bundle was staged from git SHA %s but current checkout is %s. "
            "Source hash matched, so startup is allowed.",
            built_sha,
            current_git_sha,
        )


# Static files directory (UI build output)
STATIC_DIR = get_static_dir()


def _make_lifespan(mcp_asgi_app=None):
    """Build a lifespan that optionally manages the MCP server's lifecycle."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting db-mcp UI server")
        try:
            validate_static_bundle_provenance()
        except RuntimeError as e:
            logger.warning("Static bundle validation skipped: %s", e)

        if mcp_asgi_app is not None:
            # Run the MCP ASGI app's lifespan (initializes the task group)
            mcp_lifespan = mcp_asgi_app.router.lifespan_context
            async with mcp_lifespan(mcp_asgi_app):
                yield
        else:
            yield

        logger.info("Shutting down db-mcp UI server")

    return lifespan


def create_app(mount_mcp: bool = False) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        mount_mcp: If True, mount the MCP server as an ASGI sub-app at ``/mcp``.
            Used by ``db-mcp up`` to serve everything on a single port.
    """
    mcp_asgi_app = None
    if mount_mcp:
        from db_mcp_server.server import create_mcp_server

        mcp = create_mcp_server()
        mcp_asgi_app = mcp.http_app(path="/")

    app = FastAPI(
        title="db-mcp UI Server",
        description="FastAPI server for db-mcp UI with BICP support",
        version="0.1.0",
        lifespan=_make_lifespan(mcp_asgi_app),
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
    app.include_router(runtime_router)
    app.include_router(api_router, prefix="/api")

    if mcp_asgi_app:
        app.mount("/mcp", mcp_asgi_app)

    def _serve_exported_page(*segments: str):
        page_path = STATIC_DIR.joinpath(*segments, "index.html")
        if page_path.exists():
            return FileResponse(page_path)
        return JSONResponse(
            content={"message": "UI not built. Run UI build first."},
            status_code=404,
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

    # Serve index.html for root
    @app.get("/")
    async def serve_root():
        """Redirect the root path to the connections landing page."""
        return RedirectResponse(url="/connections/")

    @app.get("/connection/new")
    @app.get("/connection/new/")
    async def serve_connection_new():
        """Serve the connection wizard shell."""
        return _serve_exported_page("connection/new")

    @app.get("/connection/{name}")
    @app.get("/connection/{name}/")
    async def serve_connection_detail(name: str):
        """Serve the connection detail shell for connection-first routes."""
        del name
        return _serve_exported_page("connection")

    @app.get("/connection/{name}/insights")
    @app.get("/connection/{name}/insights/")
    async def serve_connection_insights(name: str):
        """Serve the connection-scoped insights shell."""
        del name
        return _serve_exported_page("connection/insights")

    @app.get("/connection/{name}/knowledge")
    @app.get("/connection/{name}/knowledge/")
    async def serve_connection_knowledge(name: str):
        """Serve the connection-scoped knowledge shell."""
        del name
        return _serve_exported_page("connection/knowledge")

    # Mount static files if directory exists
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


def create_unified_app() -> FastAPI:
    """Factory for ``db-mcp up``: FastAPI + MCP on a single port."""
    return create_app(mount_mcp=True)


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
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    start_ui_server()
