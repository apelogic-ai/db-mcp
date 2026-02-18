# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for db-mcp CLI.

Build with:
    cd packages/core
    uv run pyinstaller db-mcp.spec

Or use the build script:
    uv run python scripts/build.py
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

# Get the app directory
app_dir = Path(SPECPATH)
src_dir = app_dir / "src"
resources_dir = app_dir.parent.parent / "packages" / "resources"

block_cipher = None

# Collect ALL package metadata to avoid version check failures at runtime
import importlib.metadata
from PyInstaller.utils.hooks import collect_dynamic_libs

datas = []
binaries = []

# Get all installed packages and copy their metadata
for dist in importlib.metadata.distributions():
    try:
        datas += copy_metadata(dist.metadata["Name"])
    except Exception:
        pass

# Collect lupa native libraries (Lua bindings for fakeredis)
try:
    binaries += collect_dynamic_libs("lupa")
except Exception:
    pass

# Collect fakeredis data files (commands.json, etc.)
try:
    datas += collect_data_files("fakeredis", include_py_files=False)
    # Also explicitly add commands.json to the right location
    import fakeredis
    fakeredis_dir = Path(fakeredis.__file__).parent
    datas.append((str(fakeredis_dir / "commands.json"), "fakeredis"))
except Exception:
    pass

# Include bundled playground data (chinook.db + pre-seeded context files)
data_dir = src_dir / "db_mcp" / "data"
if data_dir.exists():
    datas.append((str(data_dir), "db_mcp/data"))

# Include vault templates if they exist
if resources_dir.exists():
    datas.append((str(resources_dir / "db_mcp_app"), "resources/db_mcp_app"))

# Include UI static files if they exist
static_dir = src_dir / "db_mcp" / "static"
if static_dir.exists():
    datas.append((str(static_dir), "db_mcp/static"))

a = Analysis(
    [str(src_dir / "db_mcp" / "cli" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # CLI package and submodules
        "db_mcp.cli",
        "db_mcp.cli.main",
        "db_mcp.cli.connection",
        "db_mcp.cli.git_ops",
        "db_mcp.cli.agent_config",
        "db_mcp.cli.discovery",
        "db_mcp.cli.init_flow",
        "db_mcp.cli.utils",
        "db_mcp.cli.commands",
        "db_mcp.cli.commands.core",
        "db_mcp.cli.commands.collab",
        "db_mcp.cli.commands.traces",
        "db_mcp.cli.commands.git_cmds",
        "db_mcp.cli.commands.agents_cmd",
        "db_mcp.cli.commands.discover_cmd",
        "db_mcp.cli.commands.services",
        # SQLAlchemy dialects
        "sqlalchemy.dialects.postgresql",
        "sqlalchemy.dialects.mysql",
        "trino.sqlalchemy",
        "clickhouse_sqlalchemy",
        # Pydantic
        "pydantic",
        "pydantic_settings",
        "pydantic_core",
        # FastMCP and dependencies
        "fastmcp",
        "mcp",
        "httpx",
        "anyio",
        "starlette",
        "uvicorn",
        # Rich console
        "rich",
        "rich.console",
        "rich.panel",
        "rich.prompt",
        "rich._unicode_data",
        "rich._unicode_data.unicode17-0-0",
        "rich._unicode_data.unicode15-0-0",
        "rich._unicode_data.unicode15-1-0",
        "rich._unicode_data.unicode5-2-0",
        # Click
        "click",
        # YAML
        "yaml",
        # Fakeredis/Lua support (used by docket)
        "lupa",
        "lupa.lua51",
        "lupa.lua52",
        "lupa.lua53",
        "lupa.lua54",
        "lupa.luajit20",
        "lupa.luajit21",
        "fakeredis",
        # OpenTelemetry (for console tracing)
        "opentelemetry",
        "opentelemetry.sdk",
        "opentelemetry.sdk.trace",
        "opentelemetry.sdk.trace.export",
        "opentelemetry.trace",
        # BICP agent (for UI server)
        "bicp_agent",
        "bicp_agent.handler",
        "bicp_agent.session",
        "bicp_agent.types",
        # UI server (FastAPI)
        "db_mcp.bicp",
        "db_mcp.bicp.agent",
        "db_mcp.ui_server",
        "fastapi",
        "fastapi.middleware.cors",
        # Traces module (lazy import in _configure_observability)
        "db_mcp.traces",
        # Console module
        "db_mcp.console",
        "db_mcp.console.collector",
        "db_mcp.console.server",
        "db_mcp.console.ui",
        "db_mcp.console.exporter",
        "db_mcp.console.http_exporter",
        "db_mcp.console.instrument",
        # Other
        "email.mime.text",
        "email.mime.multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        # Exclude logfire - its Pydantic plugin breaks in PyInstaller
        # (tries to inspect source code which doesn't exist in bundle)
        "logfire",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="db-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
