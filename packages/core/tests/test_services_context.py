"""Tests for context-building services."""

from types import SimpleNamespace

from db_mcp_models import PromptInstructions, QueryExample, QueryExamples


def test_build_schema_context_formats_tables_and_tracks_schema_file_usage(monkeypatch):
    from db_mcp.services.context import build_schema_context

    class FakeSpan:
        def __init__(self) -> None:
            self.attributes = {}

        def get_attribute(self, key):
            return self.attributes.get(key)

        def set_attribute(self, key, value) -> None:
            self.attributes[key] = value

    fake_schema = SimpleNamespace(
        tables=[
            SimpleNamespace(
                full_name="analytics.orders",
                description="Customer orders",
                columns=[
                    SimpleNamespace(name="id", type="integer", description="Primary key"),
                    SimpleNamespace(name="total", type="numeric", description=None),
                ],
            )
        ]
    )
    fake_span = FakeSpan()

    monkeypatch.setattr(
        "db_mcp.services.context.load_schema_descriptions",
        lambda provider_id, connection_path=None: fake_schema,
    )
    monkeypatch.setattr("db_mcp.services.context.trace.get_current_span", lambda: fake_span)

    result = build_schema_context("analytics")

    assert "## Available Tables" in result
    assert "### analytics.orders - Customer orders" in result
    assert "  - id: integer -- Primary key" in result
    assert "  - total: numeric" in result
    assert fake_span.attributes["knowledge.files_used"] == ["schema/descriptions.yaml"]


def test_build_examples_context_formats_examples_and_tracks_example_files(monkeypatch):
    from db_mcp.services.context import build_examples_context

    class FakeSpan:
        def __init__(self) -> None:
            self.attributes = {}

        def get_attribute(self, key):
            return self.attributes.get(key)

        def set_attribute(self, key, value) -> None:
            self.attributes[key] = value

    fake_examples = QueryExamples(
        provider_id="analytics",
        examples=[
            QueryExample(
                id="orders-by-day",
                natural_language="Show orders by day",
                sql="select order_date, count(*) from orders group by 1",
            ),
            QueryExample(
                id="revenue-by-day",
                natural_language="Show revenue by day",
                sql="select order_date, sum(total) from orders group by 1",
            ),
        ],
    )
    fake_span = FakeSpan()

    monkeypatch.setattr(
        "db_mcp.services.context.load_examples",
        lambda provider_id: fake_examples,
    )
    monkeypatch.setattr("db_mcp.services.context.trace.get_current_span", lambda: fake_span)

    result = build_examples_context("analytics", limit=1)

    assert "## Query Examples" in result
    assert "Question: Show orders by day" in result
    assert "SQL: select order_date, count(*) from orders group by 1" in result
    assert "Question: Show revenue by day" not in result
    assert fake_span.attributes["knowledge.files_used"] == ["examples/orders-by-day.yaml"]


def test_build_rules_context_formats_rules_and_tracks_rules_file(monkeypatch):
    from db_mcp.services.context import build_rules_context

    class FakeSpan:
        def __init__(self) -> None:
            self.attributes = {}

        def get_attribute(self, key):
            return self.attributes.get(key)

        def set_attribute(self, key, value) -> None:
            self.attributes[key] = value

    fake_instructions = PromptInstructions(
        provider_id="analytics",
        rules=[
            "Use booked revenue, not billed revenue.",
            "Exclude internal test accounts.",
        ],
    )
    fake_span = FakeSpan()

    monkeypatch.setattr(
        "db_mcp.services.context.load_instructions",
        lambda provider_id: fake_instructions,
    )
    monkeypatch.setattr("db_mcp.services.context.trace.get_current_span", lambda: fake_span)

    result = build_rules_context("analytics")

    assert "## Business Rules" in result
    assert "- Use booked revenue, not billed revenue." in result
    assert "- Exclude internal test accounts." in result
    assert fake_span.attributes["knowledge.files_used"] == [
        "instructions/business_rules.yaml"
    ]
