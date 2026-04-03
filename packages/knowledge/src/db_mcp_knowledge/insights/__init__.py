"""Proactive insight detection for db-mcp.

Detects noteworthy patterns in traces and surfaces them as
MCP resources for the connected agent to analyze.
"""

__all__ = [
    "Insight",
    "InsightStore",
    "detect_insights",
    "load_insights",
    "mark_insights_processed",
    "save_insights",
    "scan_and_update",
    "should_suggest_insights",
]
