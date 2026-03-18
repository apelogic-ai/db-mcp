from __future__ import annotations

from db_mcp.code_runtime.native_adapter import CodeRuntimeNativeAdapter


def test_native_runtime_adapter_materializes_bootstrap(tmp_path):
    adapter = CodeRuntimeNativeAdapter(
        server_url="http://127.0.0.1:8091",
        connection="playground",
        session_id="native-session-1",
        real_python="/usr/bin/python3",
    )

    materialized = adapter.materialize(tmp_path)

    sitecustomize = (materialized.bootstrap_dir / "sitecustomize.py").read_text()
    wrapper = (materialized.wrapper_dir / "python3").read_text()

    assert materialized.env["DB_MCP_NATIVE_SERVER_URL"] == "http://127.0.0.1:8091"
    assert materialized.env["DB_MCP_NATIVE_CONNECTION"] == "playground"
    assert materialized.env["DB_MCP_NATIVE_SESSION_ID"] == "native-session-1"
    assert str(materialized.bootstrap_dir) in materialized.env["PYTHONPATH"]
    assert "builtins.dbmcp" in sitecustomize
    assert "CodeRuntimeClient" in sitecustomize
    assert 'exec "$DB_MCP_REAL_PYTHON" "$@"' in wrapper
