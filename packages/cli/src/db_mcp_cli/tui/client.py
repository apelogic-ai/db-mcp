"""REST API client for TUI polling."""

from __future__ import annotations

import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from db_mcp_cli.tui.events import FeedEvent, StatusSnapshot

logger = logging.getLogger(__name__)


class APIClient:
    """Synchronous REST client for polling the db-mcp daemon."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url.rstrip("/")
        self.last_execution_ts: float = 0.0

    def check_health(self) -> bool:
        """Return True if the daemon is reachable."""
        try:
            resp = urlopen(f"{self.base_url}/health", timeout=2)
            return resp.status == 200
        except (URLError, OSError):
            return False

    def fetch_executions(self) -> list[FeedEvent]:
        """Poll for new executions since last cursor."""
        try:
            body = json.dumps({"since": self.last_execution_ts}).encode()
            req = Request(
                f"{self.base_url}/api/traces/list",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=5)
            data = json.loads(resp.read())
        except (URLError, OSError, json.JSONDecodeError) as e:
            logger.debug("fetch_executions failed: %s", e)
            return []

        events: list[FeedEvent] = []
        traces = data.get("traces", [])
        for trace in traces:
            try:
                evt = FeedEvent.from_execution(trace)
                events.append(evt)
                ts = trace.get("created_at", 0.0)
                if ts > self.last_execution_ts:
                    self.last_execution_ts = ts
            except (KeyError, ValueError) as e:
                logger.debug("Skipping trace: %s", e)
        return events

    def fetch_status(self) -> StatusSnapshot:
        """Fetch current server status."""
        healthy = self.check_health()
        connection = ""
        try:
            body = json.dumps({}).encode()
            req = Request(
                f"{self.base_url}/api/connections/list",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=2)
            data = json.loads(resp.read())
            connections = data.get("connections", [])
            for c in connections:
                if c.get("active"):
                    connection = c.get("name", "")
                    break
        except (URLError, OSError, json.JSONDecodeError):
            pass

        return StatusSnapshot(
            connection=connection,
            server_healthy=healthy,
        )

    def confirm_execution(self, execution_id: str, action: str) -> bool:
        """Confirm or cancel a pending execution."""
        try:
            body = json.dumps({"action": action}).encode()
            req = Request(
                f"{self.base_url}/api/executions/{execution_id}/confirm",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=5)
            return resp.status == 200
        except (URLError, OSError) as e:
            logger.debug("confirm_execution failed: %s", e)
            return False

    def add_rule(self, rule_text: str) -> bool:
        """Add a business rule via the REST API."""
        try:
            body = json.dumps({"rule": rule_text}).encode()
            req = Request(
                f"{self.base_url}/api/context/add-rule",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=5)
            return resp.status == 200
        except (URLError, OSError) as e:
            logger.debug("add_rule failed: %s", e)
            return False

    def dismiss_gap(self, gap_id: str) -> bool:
        """Dismiss a knowledge gap."""
        try:
            body = json.dumps({"gapId": gap_id}).encode()
            req = Request(
                f"{self.base_url}/api/gaps/dismiss",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=5)
            return resp.status == 200
        except (URLError, OSError) as e:
            logger.debug("dismiss_gap failed: %s", e)
            return False

    def switch_connection(self, name: str) -> bool:
        """Switch the active connection."""
        try:
            body = json.dumps({"connection": name}).encode()
            req = Request(
                f"{self.base_url}/api/connections/switch",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req, timeout=5)
            return resp.status == 200
        except (URLError, OSError) as e:
            logger.debug("switch_connection failed: %s", e)
            return False
