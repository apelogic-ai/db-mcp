"""Structured logging helpers for the insider agent."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("db_mcp.insider")


def log_event(event_name: str, **payload: Any) -> None:
    """Emit one structured insider-agent log line."""
    body = {"event": event_name, **payload}
    logger.info(json.dumps(body, sort_keys=True, default=str))

