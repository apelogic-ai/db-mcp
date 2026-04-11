/**
 * Codex (OpenAI) JSONL parser.
 * Normalizes Codex trace entries into the unified TraceEntry schema.
 */

import type { TraceEntry } from "../types";

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
  if (raw.startsWith("mcp__")) return raw.replace(/__/g, ":");
  return TOOL_NAME_MAP[raw] ?? raw;
}

function extractText(content: unknown[]): string {
  const parts: string[] = [];
  for (const block of content) {
    if (typeof block === "object" && block !== null) {
      const b = block as Record<string, unknown>;
      const text = b.text ?? b.value ?? "";
      if (typeof text === "string" && text) parts.push(text);
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
    } catch { return truncate(raw, 200); }
  }
  const val = raw.cmd ?? raw.sql ?? raw.query;
  return val ? truncate(String(val), 200) : truncate(JSON.stringify(raw), 200);
}

function extractCommand(raw: string | Record<string, unknown>): string | null {
  try {
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    return parsed.cmd ? truncate(String(parsed.cmd), 200) : null;
  } catch { return null; }
}

let entryIndex = 0;

function hashId(sessionId: string, timestamp: string): string {
  return `cx:${sessionId.slice(0, 8)}:${timestamp.replace(/\D/g, "").slice(0, 14)}:${entryIndex++}`;
}

const EMPTY_TRACE: Omit<TraceEntry, "id" | "timestamp" | "agent" | "sessionId" | "entryType" | "role" | "developer" | "machine" | "project"> = {
  model: null, tokenUsage: null, toolName: null, toolCallId: null,
  filePath: null, command: null, taskSummary: null,
  gitRepo: null, gitBranch: null, gitCommit: null,
  userPrompt: null, assistantText: null, thinking: null, reasoning: null, systemPrompt: null,
  toolResultContent: null, fileContent: null, stdout: null, queryData: null,
};

/**
 * Parse a single Codex JSONL entry into a TraceEntry.
 */
export function parseCodexEntry(
  raw: Record<string, unknown>,
  sessionId: string,
  meta?: { developer?: string; machine?: string; project?: string },
): TraceEntry | null {
  const timestamp = (raw.timestamp as string) || "";
  const payload = raw.payload as Record<string, unknown> | undefined;
  if (!payload || typeof payload !== "object") return null;

  const ptype = payload.type as string | undefined;
  if (!ptype) return null;

  const id = hashId(sessionId, timestamp);
  const git = payload.git as Record<string, string> | undefined;

  const base = {
    ...EMPTY_TRACE,
    id,
    timestamp,
    agent: "codex" as const,
    sessionId,
    model: (payload.model as string) ?? null,
    developer: meta?.developer ?? "",
    machine: meta?.machine ?? "",
    project: meta?.project ?? "",
    gitRepo: git?.repository_url ?? null,
    gitBranch: git?.branch ?? null,
    gitCommit: git?.commit_hash ?? null,
  };

  // Token usage from info
  const info = payload.info as Record<string, unknown> | undefined;
  const ltu = info?.last_token_usage as Record<string, number> | undefined;
  if (ltu) {
    base.tokenUsage = {
      input: ltu.input_tokens ?? 0,
      output: ltu.output_tokens ?? 0,
      cacheRead: ltu.cached_input_tokens ?? 0,
      reasoning: ltu.reasoning_output_tokens ?? 0,
    };
  }

  // Function call
  if (ptype === "function_call") {
    const name = (payload.name as string) || "unknown";
    const args = payload.arguments ?? payload.input ?? "";
    return {
      ...base,
      entryType: "tool_call",
      role: "assistant",
      toolName: normalizeToolName(name),
      toolCallId: (payload.call_id as string) ?? null,
      command: extractCommand(args as string | Record<string, unknown>),
    };
  }

  // Function call output
  if (ptype === "function_call_output") {
    const output = payload.output ?? payload.result ?? "";
    return {
      ...base,
      entryType: "tool_result",
      role: "tool",
      toolResultContent: String(output),
      stdout: String(output),
    };
  }

  // Task complete
  if (ptype === "task_complete") {
    const msg = payload.last_agent_message;
    if (!msg || typeof msg !== "string") return null;
    return {
      ...base,
      entryType: "task_summary",
      role: "assistant",
      taskSummary: truncate(msg, 500),
      assistantText: truncate(msg, 500),
    };
  }

  // User message
  if (ptype === "message" && payload.role === "user") {
    const content = payload.content as unknown[];
    const text = Array.isArray(content) ? extractText(content) : "";
    return { ...base, entryType: "message", role: "user", userPrompt: truncate(text, 500) };
  }

  // Agent message
  if (ptype === "agent_message") {
    const content = payload.content as unknown[];
    const text = Array.isArray(content) ? extractText(content) : "";
    return { ...base, entryType: "message", role: "assistant", assistantText: truncate(text, 500) };
  }

  // Reasoning
  if (ptype === "reasoning") {
    const content = payload.content as unknown[];
    const text = Array.isArray(content) ? extractText(content) : "";
    if (!text) return null;
    return { ...base, entryType: "reasoning", role: "assistant", reasoning: truncate(text, 500) };
  }

  return null;
}

// Re-export for backward compat
export type NormalizedEntry = TraceEntry;
