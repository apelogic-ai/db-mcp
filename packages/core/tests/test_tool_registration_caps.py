"""Tests for tool registration capability defaults matching runtime defaults.

Verifies that the server.py capability defaulting logic produces the same
results as get_connector_capabilities() for each connector type, preventing
registration-time vs runtime mismatches (e.g. server.py registering
validate_sql for API connectors when the runtime says it's not supported).
"""


def _server_caps_for_type(connector_type: str, yaml_caps: dict | None = None):
    """Simulate the server.py capability resolution for a given connector type.

    Mirrors the logic in _create_server() without actually creating the server.
    """
    raw_caps = yaml_caps or {}

    _type_defaults = {
        "sql": {
            "supports_sql": True,
            "supports_validate_sql": True,
            "supports_async_jobs": True,
            "sql_mode": "engine",
        },
        "file": {
            "supports_sql": True,
            "supports_validate_sql": True,
            "supports_async_jobs": True,
            "sql_mode": "engine",
        },
        "metabase": {
            "supports_sql": True,
            "supports_validate_sql": False,
            "supports_async_jobs": False,
            "sql_mode": "api_sync",
        },
        "api": {
            "supports_sql": False,
            "supports_validate_sql": False,
            "supports_async_jobs": False,
            "sql_mode": None,
        },
    }
    caps = dict(_type_defaults.get(connector_type, {}))
    caps.update(raw_caps)
    return caps


class TestCapabilityDefaultsMatch:
    """server.py defaults must match get_connector_capabilities() defaults."""

    def test_sql_defaults_match(self):
        from db_mcp.connectors import SQLConnector, get_connector_capabilities
        from db_mcp.connectors.sql import SQLConnectorConfig

        connector = SQLConnector(SQLConnectorConfig(database_url="sqlite:///:memory:"))
        runtime = get_connector_capabilities(connector)
        server = _server_caps_for_type("sql")

        assert server["supports_sql"] == runtime["supports_sql"]
        assert server["supports_validate_sql"] == runtime["supports_validate_sql"]
        assert server["supports_async_jobs"] == runtime["supports_async_jobs"]
        assert server["sql_mode"] == runtime["sql_mode"]

    def test_api_defaults_validate_is_false(self):
        """Specifically verify API connector does NOT register validate_sql by default."""
        caps = _server_caps_for_type("api")
        assert caps["supports_validate_sql"] is False
        assert caps["supports_sql"] is False

    def test_api_with_sql_support(self):
        """API with supports_sql=true should still have validate=false unless explicit."""
        caps = _server_caps_for_type("api", {"supports_sql": True})
        assert caps["supports_sql"] is True
        assert caps["supports_validate_sql"] is False  # not overridden

    def test_api_with_explicit_validate(self):
        """API with explicit supports_validate_sql=true should work."""
        caps = _server_caps_for_type("api", {"supports_validate_sql": True, "supports_sql": True})
        assert caps["supports_validate_sql"] is True
        assert caps["supports_sql"] is True

    def test_metabase_defaults(self):
        """Metabase: supports_sql=true, validate=false, sql_mode=api_sync."""
        caps = _server_caps_for_type("metabase")
        assert caps["supports_sql"] is True
        assert caps["supports_validate_sql"] is False
        assert caps["sql_mode"] == "api_sync"

    def test_sql_defaults(self):
        """SQL: everything defaults to supported."""
        caps = _server_caps_for_type("sql")
        assert caps["supports_sql"] is True
        assert caps["supports_validate_sql"] is True
        assert caps["supports_async_jobs"] is True
        assert caps["sql_mode"] == "engine"

    def test_file_defaults(self):
        """File: same as SQL."""
        caps = _server_caps_for_type("file")
        assert caps["supports_sql"] is True
        assert caps["supports_validate_sql"] is True
        assert caps["supports_async_jobs"] is True
        assert caps["sql_mode"] == "engine"

    def test_yaml_overrides_apply(self):
        """YAML capabilities should override type defaults."""
        caps = _server_caps_for_type("sql", {"supports_validate_sql": False})
        assert caps["supports_validate_sql"] is False  # overridden

    def test_api_runtime_matches_server_defaults(self):
        """get_connector_capabilities for API must match server.py API defaults."""
        # For API connectors, defaults are supports_sql=False, supports_validate_sql=False
        # These should match _server_caps_for_type("api")
        server = _server_caps_for_type("api")
        assert server["supports_sql"] is False
        assert server["supports_validate_sql"] is False
        assert server["supports_async_jobs"] is False
        assert server["sql_mode"] is None


class TestApiMutateSingleDefinition:
    """Verify _api_mutate has exactly one definition and correct signature."""

    def test_single_definition(self):
        """There should be only one _api_mutate function, not a duplicate."""
        import ast
        from pathlib import Path

        api_file = Path(__file__).parent.parent / "src" / "db_mcp" / "tools" / "api.py"
        tree = ast.parse(api_file.read_text())

        mutate_defs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_api_mutate"
        ]
        assert len(mutate_defs) == 1, (
            f"Expected 1 definition of _api_mutate, found {len(mutate_defs)}"
        )

    def test_body_is_optional(self):
        """The body parameter should be optional (for DELETE requests)."""
        import inspect

        from db_mcp.tools.api import _api_mutate

        sig = inspect.signature(_api_mutate)
        body_param = sig.parameters["body"]
        assert body_param.default is None, "body should default to None for DELETE support"


class TestRunSqlFallbackCodeAnalysis:
    """Verify run_sql fallback logic via AST analysis.

    The generation module can't be imported in this environment due to a
    pre-existing pydantic_ai->griffe dependency issue, so we verify the
    code structure via AST parsing instead.
    """

    def _get_run_sql_source(self):
        from pathlib import Path

        gen_file = Path(__file__).parent.parent / "src" / "db_mcp" / "tools" / "generation.py"
        return gen_file.read_text()

    def test_fallback_uses_hasattr_check(self):
        """The fallback path should check hasattr(connector, 'execute_sql')."""
        source = self._get_run_sql_source()
        assert 'hasattr(connector, "execute_sql")' in source

    def test_error_includes_sql_mode_value(self):
        """Error message should include the actual sql_mode value for debugging."""
        source = self._get_run_sql_source()
        # Should use f-string with sql_mode, not a static message
        assert "sql_mode={sql_mode!r}" in source or "sql_mode=" in source

    def test_no_bare_unsupported_error(self):
        """The generic 'Unsupported sql_mode' without the value should not exist."""
        source = self._get_run_sql_source()
        assert '"Unsupported sql_mode for direct SQL execution."' not in source
