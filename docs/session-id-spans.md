# Session ID in OTel Spans

## Status: Planned (not yet implemented)

## Problem

There's no session/conversation ID in the current span attributes, so we can't group traces into sessions/conversations in the Traces UI.

## Findings

### FastMCP Context already exposes `session_id`

**File**: `.venv/.../fastmcp/server/context.py`

```python
@property
def session_id(self) -> str | None:
    return str(id(self.session))  # Python object id
```

Also available: `context.client_id` → e.g. `"claude-desktop"`.

### Middleware API mismatch

The current `TracingMiddleware` in `instrument.py` uses the **old** FastMCP middleware pattern:

```python
async def on_call_tool(self, context, call_next):
    ...
    result = await call_next(context)
```

The installed FastMCP version uses `asynccontextmanager`-based hooks:

```python
@contextlib.asynccontextmanager
async def on_call_tool(self, request: ToolRequest, context: Context):
    yield request  # before/after pattern
```

### Implementation plan

1. **Rewrite `TracingMiddleware`** to use the current `asynccontextmanager` API
2. **Extract `context.session_id` and `context.client_id`** in every hook
3. **Add `session.id` and `client.id`** as span attributes — they flow through all exporters automatically
4. **UI**: Add session grouping toggle in Traces page, show session duration

### Notes

- `session_id` is `str(id(session))` — a Python memory address, unique per session within a process lifetime, resets on restart
- Could generate proper UUIDs via `on_initialize` hook if persistent IDs are needed
- All three exporters (HttpSpanExporter, JSONLSpanExporter, ConsoleSpanExporter) already preserve all attributes, so `session.id` flows through with no exporter changes
