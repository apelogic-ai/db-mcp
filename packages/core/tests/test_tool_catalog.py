"""Tests for tool catalog discovery and SDK rendering."""

from db_mcp_server.tool_catalog import render_python_sdk, search_tool_catalog


def test_search_tool_catalog_ranks_name_matches_first():
    catalog = [
        {
            "name": "run_sql",
            "description": "Execute SQL query",
            "category": "query",
            "required": ["connection"],
            "properties": {},
        },
        {
            "name": "list_tables",
            "description": "List all tables for a schema",
            "category": "schema",
            "required": [],
            "properties": {},
        },
    ]

    matches = search_tool_catalog(catalog, query="sql", limit=5)
    assert matches[0]["name"] == "run_sql"


def test_render_python_sdk_generates_async_wrapper_methods():
    catalog = [
        {
            "name": "run_sql",
            "description": "Run a SQL statement.",
            "category": "query",
            "required": ["connection"],
            "properties": {
                "connection": {"type": "string"},
                "sql": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False},
            },
        }
    ]

    code = render_python_sdk(catalog)
    assert "class DbMcpTools:" in code
    assert "async def run_sql(" in code
    assert 'return await self._call_tool("run_sql", payload)' in code
    assert 'payload["connection"] = connection' in code
