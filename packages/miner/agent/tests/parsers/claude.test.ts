import { describe, it, expect } from "vitest";
import { parseClaudeEntry, type NormalizedEntry } from "../../src/parsers/claude";

describe("parseClaudeEntry", () => {
  const sessionId = "abc-123";

  it("parses a user message", () => {
    const raw = {
      type: "user",
      timestamp: "2026-04-08T10:00:00.000Z",
      message: {
        role: "user",
        content: [{ type: "text", text: "Fix the bug in query.py" }],
      },
    };
    const entry = parseClaudeEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("message");
    expect(entry!.role).toBe("user");
    expect(entry!.contentPreview).toBe("Fix the bug in query.py");
    expect(entry!.agent).toBe("claude_code");
    expect(entry!.sessionId).toBe(sessionId);
  });

  it("parses an assistant message with tool_use", () => {
    const raw = {
      type: "assistant",
      timestamp: "2026-04-08T10:00:01.000Z",
      message: {
        role: "assistant",
        content: [
          { type: "tool_use", name: "Bash", input: { command: "uv run pytest tests/" } },
        ],
        usage: { input_tokens: 1000, output_tokens: 200, cache_read_input_tokens: 5000 },
      },
    };
    const entries = parseClaudeEntry(raw, sessionId);
    expect(entries).not.toBeNull();
    expect(entries!.entryType).toBe("tool_call");
    expect(entries!.toolName).toBe("Bash");
    expect(entries!.toolInputSummary).toContain("uv run pytest");
    expect(entries!.tokenUsage).toEqual({
      input: 1000,
      output: 200,
      cacheRead: 5000,
    });
  });

  it("normalizes tool names", () => {
    const raw = {
      type: "assistant",
      timestamp: "2026-04-08T10:00:01.000Z",
      message: {
        content: [
          { type: "tool_use", name: "mcp__db-mcp__run_sql", input: { sql: "SELECT 1" } },
        ],
      },
    };
    const entry = parseClaudeEntry(raw, sessionId);
    expect(entry!.toolName).toBe("mcp:db-mcp:run_sql");
  });

  it("parses a tool_result", () => {
    const raw = {
      type: "user",
      timestamp: "2026-04-08T10:00:02.000Z",
      message: {
        content: [
          {
            type: "tool_result",
            tool_use_id: "tool_123",
            content: "3 passed, 0 failed",
          },
        ],
      },
    };
    const entry = parseClaudeEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("tool_result");
    expect(entry!.contentPreview).toContain("3 passed");
  });

  it("extracts tool success from tool_result content", () => {
    const passing = {
      type: "user",
      timestamp: "2026-04-08T10:00:02.000Z",
      message: {
        content: [{ type: "tool_result", content: "All tests passed" }],
      },
    };
    expect(parseClaudeEntry(passing, sessionId)!.toolSuccess).toBe(true);

    const failing = {
      type: "user",
      timestamp: "2026-04-08T10:00:02.000Z",
      message: {
        content: [{ type: "tool_result", content: "Error: file not found", is_error: true }],
      },
    };
    expect(parseClaudeEntry(failing, sessionId)!.toolSuccess).toBe(false);
  });

  it("returns null for non-message entries", () => {
    expect(parseClaudeEntry({}, sessionId)).toBeNull();
    expect(parseClaudeEntry({ type: "unknown" }, sessionId)).toBeNull();
  });

  it("truncates content preview to 200 chars", () => {
    const longText = "a".repeat(500);
    const raw = {
      type: "user",
      timestamp: "2026-04-08T10:00:00.000Z",
      message: {
        content: [{ type: "text", text: longText }],
      },
    };
    const entry = parseClaudeEntry(raw, sessionId);
    expect(entry!.contentPreview!.length).toBeLessThanOrEqual(200);
  });

  it("includes timestamp", () => {
    const raw = {
      type: "user",
      timestamp: "2026-04-08T10:30:00.000Z",
      message: { content: [{ type: "text", text: "hello" }] },
    };
    const entry = parseClaudeEntry(raw, sessionId);
    expect(entry!.timestamp).toBe("2026-04-08T10:30:00.000Z");
  });
});
