"""TUI feed event model and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

_TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


@dataclass
class StatusSnapshot:
    """Data bag for the status bar."""

    connection: str = ""
    server_healthy: bool = False
    execution_count: int = 0


@dataclass
class FeedEvent:
    """A single event rendered in the TUI feed."""

    id: str
    type: str  # "query", "confirm_required", "gap", "rule_added", ...
    headline: str
    timestamp: datetime
    sub_lines: list[str] = field(default_factory=list)
    pending_action: str | None = None
    done: bool = False

    def render(self) -> str:
        """Render this event as Rich markup for the feed."""
        bullet = "[bold green]\u2714[/]" if self.done else "[bold]\u25cf[/]"
        lines = [f"{bullet} {self.headline}"]
        for sub in self.sub_lines:
            lines.append(f"  [dim]\u23bf[/]  {sub}")
        return "\n".join(lines)

    @classmethod
    def from_execution(cls, execution: dict) -> FeedEvent:
        """Build a FeedEvent from an execution store dict."""
        state = execution.get("state", "")
        done = state in _TERMINAL_STATES
        sql = execution.get("sql", "") or ""
        headline = sql[:80] + ("..." if len(sql) > 80 else "") if sql else f"[{state}]"

        sub_lines: list[str] = []
        if done:
            duration = execution.get("duration_ms")
            rows = execution.get("rows_returned", 0)
            parts = []
            if state == "succeeded":
                parts.append("\u2714 done")
            elif state == "failed":
                parts.append("\u2718 failed")
            else:
                parts.append(state)
            if duration is not None:
                parts.append(f"{duration:.0f}ms")
            parts.append(f"{rows:,} rows")
            sub_lines.append("  |  ".join(parts))

        ts = execution.get("created_at", 0.0)
        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(
            timezone.utc
        )

        return cls(
            id=execution["execution_id"],
            type="query",
            headline=headline,
            timestamp=timestamp,
            sub_lines=sub_lines,
            done=done,
        )
