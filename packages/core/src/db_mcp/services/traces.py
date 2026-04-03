"""Trace and observability services.

Provides service functions for listing live/historical traces, clearing the
live collector, and querying available trace dates.  The BICP agent delegates
to these functions instead of embedding the logic inline.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Internal helpers — thin wrappers around third-party calls that are easy
# to mock in tests.
# ---------------------------------------------------------------------------


def _get_collector():
    from db_mcp.console.collector import get_collector

    return get_collector()


def _is_traces_enabled() -> bool:
    from db_mcp.traces import is_traces_enabled

    return is_traces_enabled()


def _get_user_id() -> str | None:
    from db_mcp.traces import get_user_id_from_config

    return get_user_id_from_config()


def _get_traces_dir(connection_path: Path, user_id: str) -> Path:
    from db_mcp.traces import get_traces_dir

    return get_traces_dir(connection_path, user_id)


def _read_traces_from_jsonl(file_path: Path, limit: int | None = 500) -> list[dict]:
    from db_mcp.traces_reader import read_traces_from_jsonl

    return read_traces_from_jsonl(file_path, limit=limit)


def _list_trace_dates_from_dir(connection_path: Path, user_id: str) -> list[str]:
    from db_mcp.traces_reader import list_trace_dates

    return list_trace_dates(connection_path, user_id)


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------


def list_traces(
    source: str = "live",
    connection_path: Path | None = None,
    date_str: str | None = None,
    limit: int | None = None,
) -> dict:
    """List traces from the live collector or historical JSONL files.

    Args:
        source: "live" to read from the in-memory collector; "historical" to
            read from on-disk JSONL files for a specific date.
        connection_path: Required for *historical* source — the connection's
            vault directory (used to locate the JSONL files).
        date_str: Date string "YYYY-MM-DD" for historical source.  Defaults
            to today when *None*.
        limit: Maximum traces to return.  Defaults to 50 for live and 500 for
            historical when *None*.

    Returns:
        {"success": bool, "traces": list[dict], "source": str, "error": str}
    """
    if source == "live":
        effective_limit = limit if limit is not None else 50
        traces = _get_collector().get_traces(limit=effective_limit)
        return {"success": True, "traces": traces, "source": "live"}

    if source == "historical":
        if not _is_traces_enabled():
            return {
                "success": False,
                "traces": [],
                "source": "historical",
                "error": "Traces are not enabled",
            }

        user_id = _get_user_id()
        if not user_id:
            return {
                "success": False,
                "traces": [],
                "source": "historical",
                "error": "No user_id configured",
            }

        if connection_path is None:
            return {
                "success": False,
                "traces": [],
                "source": "historical",
                "error": "No active connection",
            }

        effective_limit = limit if limit is not None else 500
        effective_date = date_str or datetime.now().strftime("%Y-%m-%d")
        traces_dir = _get_traces_dir(connection_path, user_id)
        file_path = traces_dir / f"{effective_date}.jsonl"
        traces = _read_traces_from_jsonl(file_path, limit=effective_limit)
        return {"success": True, "traces": traces, "source": "historical"}

    return {"success": False, "traces": [], "error": f"Unknown source: {source}"}


def clear_traces() -> dict:
    """Clear all traces from the live in-memory span collector.

    Returns:
        {"success": True}
    """
    _get_collector().clear()
    return {"success": True}


def get_trace_dates(connection_path: Path | None) -> dict:
    """List available historical trace dates for a connection.

    Args:
        connection_path: The connection's vault directory.  When *None* the
            function returns an empty list (no active connection).

    Returns:
        {"success": True, "enabled": bool, "dates": list[str]}
    """
    if not _is_traces_enabled():
        return {"success": True, "enabled": False, "dates": []}

    user_id = _get_user_id()
    if not user_id:
        return {"success": True, "enabled": True, "dates": []}

    if connection_path is None:
        return {"success": True, "enabled": True, "dates": []}

    dates = _list_trace_dates_from_dir(connection_path, user_id)
    return {"success": True, "enabled": True, "dates": dates}
