"""Tests for insider-agent SQLite store behavior."""

from db_mcp.insider.models import AgentEvent
from db_mcp.insider.store import InsiderStore


def test_store_dedupes_events_by_connection_type_and_schema_digest(tmp_path):
    store = InsiderStore(tmp_path / "insider.db")
    event = AgentEvent(
        event_id="evt-1",
        connection="playground",
        event_type="new_connection",
        schema_digest="abc",
        payload={"source": "test"},
    )
    assert store.create_event(event) is True
    assert store.create_event(
        AgentEvent(
            event_id="evt-2",
            connection="playground",
            event_type="new_connection",
            schema_digest="abc",
            payload={"source": "test"},
        )
    ) is False

    rows = store.list_events("playground")
    assert len(rows) == 1
    assert rows[0]["event_id"] == "evt-1"
