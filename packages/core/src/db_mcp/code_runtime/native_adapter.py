"""Native Python bootstrap adapter for host-bound db-mcp runtime sessions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from shutil import which


@dataclass(frozen=True)
class NativeRuntimeMaterialization:
    """Materialized bootstrap files and environment for one native runtime session."""

    bootstrap_dir: Path
    wrapper_dir: Path
    capture_dir: Path
    env: dict[str, str]


@dataclass(frozen=True)
class CodeRuntimeNativeAdapter:
    """Inject a live `dbmcp` object into Python via `sitecustomize`."""

    server_url: str
    connection: str
    session_id: str
    real_python: str | None = None

    def materialize(self, workdir: Path) -> NativeRuntimeMaterialization:
        bootstrap_dir = workdir / ".native-runtime"
        wrapper_dir = workdir / ".runtime-bin"
        capture_dir = workdir / "runtime-captures"
        bootstrap_dir.mkdir(parents=True, exist_ok=True)
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        capture_dir.mkdir(parents=True, exist_ok=True)

        (bootstrap_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE_TEMPLATE)
        wrapper_path = wrapper_dir / "python3"
        wrapper_path.write_text(_PYTHON_WRAPPER_TEMPLATE)
        wrapper_path.chmod(0o755)

        path_parts = [str(wrapper_dir)]
        current_path = os.environ.get("PATH")
        if current_path:
            path_parts.append(current_path)

        pythonpath_parts = [str(bootstrap_dir), str(Path(__file__).resolve().parents[2])]
        current_pythonpath = os.environ.get("PYTHONPATH")
        if current_pythonpath:
            pythonpath_parts.append(current_pythonpath)

        env = {
            "PATH": os.pathsep.join(path_parts),
            "PYTHONPATH": os.pathsep.join(pythonpath_parts),
            "DB_MCP_REAL_PYTHON": self.real_python or which("python3") or "python3",
            "DB_MCP_NATIVE_SERVER_URL": self.server_url,
            "DB_MCP_NATIVE_CONNECTION": self.connection,
            "DB_MCP_NATIVE_SESSION_ID": self.session_id,
            "DB_MCP_BENCH_RUNTIME_LOG": str(workdir / "runtime-invocations.jsonl"),
            "DB_MCP_BENCH_RUNTIME_CAPTURE_DIR": str(capture_dir),
        }
        return NativeRuntimeMaterialization(
            bootstrap_dir=bootstrap_dir,
            wrapper_dir=wrapper_dir,
            capture_dir=capture_dir,
            env=env,
        )


_SITECUSTOMIZE_TEMPLATE = """\
from __future__ import annotations

import builtins
import os

from db_mcp.code_runtime.client import CodeRuntimeClient

_client = CodeRuntimeClient(os.environ["DB_MCP_NATIVE_SERVER_URL"])
_session = _client.create_session(
    os.environ["DB_MCP_NATIVE_CONNECTION"],
    session_id=os.environ["DB_MCP_NATIVE_SESSION_ID"],
)
builtins.dbmcp = _session.sdk()
"""


_PYTHON_WRAPPER_TEMPLATE = """\
#!/bin/sh
set -eu

native_temp_file=""

if [ "$#" -eq 0 ]; then
  native_temp_file="${TMPDIR:-/tmp}/dbmcp-runtime-native-$$.py"
  cat > "$native_temp_file"
  set -- "$native_temp_file"
elif [ "$1" = "-" ]; then
  native_temp_file="${TMPDIR:-/tmp}/dbmcp-runtime-native-$$.py"
  cat > "$native_temp_file"
  shift
  set -- "$native_temp_file" "$@"
fi

"$DB_MCP_REAL_PYTHON" - "$@" <<'PY'
import json
import os
import shutil
import sys
from pathlib import Path

argv = sys.argv[1:]
log_path = Path(os.environ["DB_MCP_BENCH_RUNTIME_LOG"])
capture_dir = Path(os.environ["DB_MCP_BENCH_RUNTIME_CAPTURE_DIR"])
capture_dir.mkdir(parents=True, exist_ok=True)

record = {"argv": argv, "cwd": os.getcwd()}
file_arg = next((arg for arg in argv if not arg.startswith("-")), None)
if file_arg:
    file_path = Path(file_arg)
    record["file"] = str(file_path)
    if file_path.exists():
        capture_path = capture_dir / f"{len(list(capture_dir.iterdir())):03d}-{file_path.name}"
        shutil.copyfile(file_path, capture_path)
        record["captured_file"] = str(capture_path)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
PY

exec "$DB_MCP_REAL_PYTHON" "$@"
"""
