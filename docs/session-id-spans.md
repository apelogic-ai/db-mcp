# Session ID in OTel Spans

## Status: Implemented

## What was done

Added `session.id` and `client.id` span attributes to all MCP protocol traces via the `TracingMiddleware` in `instrument.py`.

### How it works

- `MiddlewareContext.fastmcp_context` provides access to the FastMCP `Context` object
- `Context.session_id` returns a UUID (persisted on the session object via `_fastmcp_id`, or derived from MCP session headers)
- `Context.client_id` returns the client name (e.g. `"claude-desktop"`)
- `_extract_session_attrs(context)` extracts both and adds them to every span

### Attributes added

| Attribute | Value | Example |
|-----------|-------|---------|
| `session.id` | UUID string | `"a1b2c3d4-..."` |
| `client.id` | Client name | `"claude-desktop"` |

These appear on every span (tool calls, list operations, initialize, etc.) and flow through all exporters automatically.

### Future: UI session grouping

With `session.id` on all spans, the Traces UI can optionally group traces by session to show conversation-level views. This is a UI-only change — the data is already there.
