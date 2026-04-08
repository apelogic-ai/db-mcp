/**
 * Codex (OpenAI) JSONL parser.
 * Normalizes Codex trace entries into the unified schema.
 */

export interface NormalizedEntry {
  id: string;
  timestamp: string;
  agent: "codex";
  sessionId: string;
  entryType: "message" | "tool_call" | "tool_result" | "reasoning" | "task_summary";
  role: "user" | "assistant" | "system" | "tool";
  toolName: string | null;
  toolInputSummary: string | null;
  toolSuccess: boolean | null;
  contentPreview: string | null;
  tokenUsage: null; // Codex doesn't log per-entry tokens
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) : s;
}

const TOOL_NAME_MAP: Record<string, string> = {
  exec_command: "shell",
  shell_command: "shell",
  apply_patch: "edit",
  write_stdin: "stdin",
  update_plan: "plan",
  request_user_input: "ask_user",
  read_thread_terminal: "terminal_read",
  view_image: "view_image",
};

function normalizeToolName(raw: string): string {
  if (raw.startsWith("mcp__")) {
    return raw.replace(/__/g, ":");
  }
  return TOOL_NAME_MAP[raw] ?? raw;
}

function extractText(content: unknown[]): string {
  const parts: string[] = [];
  for (const block of content) {
    if (typeof block === "object" && block !== null) {
      const b = block as Record<string, unknown>;
      const text = b.text ?? b.value ?? "";
      if (typeof text === "string" && text) {
        parts.push(text);
      }
    }
  }
  return parts.join("");
}

function parseArgs(raw: string | Record<string, unknown>): string {
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const val = parsed.cmd ?? parsed.sql ?? parsed.query ?? parsed.patch ?? parsed.code;
      return val ? truncate(String(val), 200) : truncate(raw, 200);
    } catch {
      return truncate(raw, 200);
    }
  }
  const val = raw.cmd ?? raw.sql ?? raw.query;
  return val ? truncate(String(val), 200) : truncate(JSON.stringify(raw), 200);
}

let entryIndex = 0;

function hashId(sessionId: string, timestamp: string): string {
  return `cx:${sessionId.slice(0, 8)}:${timestamp.replace(/\D/g, "").slice(0, 14)}:${entryIndex++}`;
}

/**
 * Parse a single Codex JSONL entry into a normalized entry.
 * Returns null if the entry is not parseable.
 */
export function parseCodexEntry(
  raw: Record<string, unknown>,
  sessionId: string,
): NormalizedEntry | null {
  const timestamp = (raw.timestamp as string) || "";
  const payload = raw.payload as Record<string, unknown> | undefined;
  if (!payload || typeof payload !== "object") return null;

  const ptype = payload.type as string | undefined;
  if (!ptype) return null;

  const id = hashId(sessionId, timestamp);

  // Function call (tool invocation)
  if (ptype === "function_call") {
    const name = (payload.name as string) || "unknown";
    const args = payload.arguments ?? payload.input ?? "";
    return {
      id,
      timestamp,
      agent: "codex",
      sessionId,
      entryType: "tool_call",
      role: "assistant",
      toolName: normalizeToolName(name),
      toolInputSummary: parseArgs(args as string | Record<string, unknown>),
      toolSuccess: null,
      contentPreview: null,
      tokenUsage: null,
    };
  }

  // Function call output (tool result)
  if (ptype === "function_call_output") {
    const output = payload.output ?? payload.result ?? "";
    const preview = truncate(String(output), 200);
    return {
      id,
      timestamp,
      agent: "codex",
      sessionId,
      entryType: "tool_result",
      role: "tool",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: null,
      contentPreview: preview,
      tokenUsage: null,
    };
  }

  // Task complete (summary)
  if (ptype === "task_complete") {
    const msg = payload.last_agent_message;
    if (!msg || typeof msg !== "string") return null;
    return {
      id,
      timestamp,
      agent: "codex",
      sessionId,
      entryType: "task_summary",
      role: "assistant",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: null,
      contentPreview: truncate(msg, 200),
      tokenUsage: null,
    };
  }

  // User message
  if (ptype === "message" && payload.role === "user") {
    const content = payload.content as unknown[];
    const text = Array.isArray(content) ? extractText(content) : "";
    return {
      id,
      timestamp,
      agent: "codex",
      sessionId,
      entryType: "message",
      role: "user",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: null,
      contentPreview: truncate(text, 200),
      tokenUsage: null,
    };
  }

  // Agent message
  if (ptype === "agent_message") {
    const content = payload.content as unknown[];
    const text = Array.isArray(content) ? extractText(content) : "";
    return {
      id,
      timestamp,
      agent: "codex",
      sessionId,
      entryType: "message",
      role: "assistant",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: null,
      contentPreview: truncate(text, 200),
      tokenUsage: null,
    };
  }

  // Reasoning
  if (ptype === "reasoning") {
    const content = payload.content as unknown[];
    const text = Array.isArray(content) ? extractText(content) : "";
    if (!text) return null;
    return {
      id,
      timestamp,
      agent: "codex",
      sessionId,
      entryType: "reasoning",
      role: "assistant",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: null,
      contentPreview: truncate(text, 200),
      tokenUsage: null,
    };
  }

  return null;
}
