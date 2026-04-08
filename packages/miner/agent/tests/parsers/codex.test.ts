import { describe, it, expect } from "vitest";
import { parseCodexEntry, type NormalizedEntry } from "../../src/parsers/codex";

describe("parseCodexEntry", () => {
  const sessionId = "codex-session-1";

  it("parses a function_call", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:00.000Z",
      type: "response_item",
      payload: {
        type: "function_call",
        name: "exec_command",
        arguments: '{"cmd":"ls -la","workdir":"/tmp"}',
        call_id: "call_123",
      },
    };
    const entry = parseCodexEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("tool_call");
    expect(entry!.toolName).toBe("shell");
    expect(entry!.toolInputSummary).toContain("ls -la");
    expect(entry!.agent).toBe("codex");
  });

  it("normalizes exec_command to shell", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:00.000Z",
      type: "response_item",
      payload: { type: "function_call", name: "exec_command", arguments: '{"cmd":"pwd"}' },
    };
    expect(parseCodexEntry(raw, sessionId)!.toolName).toBe("shell");
  });

  it("normalizes apply_patch to edit", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:00.000Z",
      type: "response_item",
      payload: { type: "function_call", name: "apply_patch", arguments: '{"patch":"..."}' },
    };
    expect(parseCodexEntry(raw, sessionId)!.toolName).toBe("edit");
  });

  it("preserves MCP tool names with prefix", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:00.000Z",
      type: "response_item",
      payload: {
        type: "function_call",
        name: "mcp__db-mcp__run_sql",
        arguments: '{"sql":"SELECT 1"}',
      },
    };
    expect(parseCodexEntry(raw, sessionId)!.toolName).toBe("mcp:db-mcp:run_sql");
  });

  it("parses a function_call_output", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:01.000Z",
      type: "response_item",
      payload: {
        type: "function_call_output",
        output: "total 42\ndrwxr-xr-x  5 user staff 160 Apr 8 file.txt",
        call_id: "call_123",
      },
    };
    const entry = parseCodexEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("tool_result");
    expect(entry!.contentPreview).toContain("total 42");
  });

  it("parses a task_complete as task_summary", () => {
    const raw = {
      timestamp: "2026-04-08T12:30:00.000Z",
      type: "event_msg",
      payload: {
        type: "task_complete",
        turn_id: "turn_abc",
        last_agent_message: "Fixed the CORS issue by adding the correct headers.",
      },
    };
    const entry = parseCodexEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("task_summary");
    expect(entry!.contentPreview).toContain("CORS");
  });

  it("parses a user message", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:00.000Z",
      type: "response_item",
      payload: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text: "Fix the login page" }],
      },
    };
    const entry = parseCodexEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("message");
    expect(entry!.role).toBe("user");
    expect(entry!.contentPreview).toBe("Fix the login page");
  });

  it("parses an agent_message", () => {
    const raw = {
      timestamp: "2026-04-08T12:01:00.000Z",
      type: "response_item",
      payload: {
        type: "agent_message",
        content: [{ type: "output_text", text: "I've fixed the login page." }],
      },
    };
    const entry = parseCodexEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("message");
    expect(entry!.role).toBe("assistant");
  });

  it("parses reasoning entries", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:30.000Z",
      type: "response_item",
      payload: {
        type: "reasoning",
        content: [{ type: "text", text: "The user wants me to check CORS headers..." }],
      },
    };
    const entry = parseCodexEntry(raw, sessionId);
    expect(entry).not.toBeNull();
    expect(entry!.entryType).toBe("reasoning");
    expect(entry!.contentPreview).toContain("CORS");
  });

  it("returns null for token_count entries", () => {
    const raw = {
      timestamp: "2026-04-08T12:00:00.000Z",
      type: "event_msg",
      payload: { type: "token_count", rate_limits: {} },
    };
    expect(parseCodexEntry(raw, sessionId)).toBeNull();
  });

  it("returns null for unparseable entries", () => {
    expect(parseCodexEntry({}, sessionId)).toBeNull();
    expect(parseCodexEntry({ type: "unknown" }, sessionId)).toBeNull();
  });
});
