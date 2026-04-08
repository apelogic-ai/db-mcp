/**
 * Claude Code JSONL parser.
 * Normalizes Claude Code trace entries into the unified schema.
 */

export interface NormalizedEntry {
  id: string;
  timestamp: string;
  agent: "claude_code";
  sessionId: string;
  entryType: "message" | "tool_call" | "tool_result" | "reasoning";
  role: "user" | "assistant" | "system" | "tool";
  toolName: string | null;
  toolInputSummary: string | null;
  toolSuccess: boolean | null;
  contentPreview: string | null;
  tokenUsage: { input: number; output: number; cacheRead: number } | null;
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) : s;
}

function normalizeToolName(raw: string): string {
  // mcp__db-mcp__run_sql → mcp:db-mcp:run_sql
  return raw.replace(/__/g, ":");
}

function extractText(content: unknown[]): string {
  const parts: string[] = [];
  for (const block of content) {
    if (typeof block === "string") {
      parts.push(block);
    } else if (typeof block === "object" && block !== null) {
      const b = block as Record<string, unknown>;
      if (b.type === "text" && typeof b.text === "string") {
        parts.push(b.text);
      }
    }
  }
  return parts.join("");
}

function hashId(sessionId: string, timestamp: string, index: number): string {
  // Simple deterministic ID — not cryptographic, just dedup
  return `cc:${sessionId.slice(0, 8)}:${timestamp.replace(/\D/g, "").slice(0, 14)}:${index}`;
}

let entryIndex = 0;

/**
 * Parse a single Claude Code JSONL entry into a normalized entry.
 * Returns null if the entry is not a parseable message.
 */
export function parseClaudeEntry(
  raw: Record<string, unknown>,
  sessionId: string
): NormalizedEntry | null {
  const entryType = raw.type as string | undefined;
  const timestamp = (raw.timestamp as string) || "";
  const message = raw.message as Record<string, unknown> | undefined;

  if (!message || (entryType !== "user" && entryType !== "assistant")) {
    return null;
  }

  const content = message.content as unknown[];
  if (!Array.isArray(content) || content.length === 0) return null;

  const usage = message.usage as Record<string, number> | undefined;
  const tokenUsage = usage?.input_tokens
    ? {
        input: usage.input_tokens || 0,
        output: usage.output_tokens || 0,
        cacheRead: usage.cache_read_input_tokens || 0,
      }
    : null;

  const firstBlock = content[0] as Record<string, unknown>;
  const blockType = firstBlock?.type as string;
  const id = hashId(sessionId, timestamp, entryIndex++);

  // Tool call (assistant sends tool_use)
  if (blockType === "tool_use") {
    const rawName = (firstBlock.name as string) || "unknown";
    const input = firstBlock.input as Record<string, unknown> | undefined;
    let inputSummary: string | null = null;
    if (input) {
      // Pick the most interesting field for the summary
      const val =
        input.command ?? input.sql ?? input.query ?? input.pattern ??
        input.file_path ?? input.endpoint ?? input.url;
      inputSummary = val ? truncate(String(val), 200) : truncate(JSON.stringify(input), 200);
    }

    return {
      id,
      timestamp,
      agent: "claude_code",
      sessionId,
      entryType: "tool_call",
      role: "assistant",
      toolName: normalizeToolName(rawName),
      toolInputSummary: inputSummary,
      toolSuccess: null,
      contentPreview: null,
      tokenUsage,
    };
  }

  // Tool result (user sends tool_result)
  if (blockType === "tool_result") {
    const resultContent = firstBlock.content;
    const isError = firstBlock.is_error === true;
    let preview: string | null = null;

    if (typeof resultContent === "string") {
      preview = truncate(resultContent, 200);
    } else if (Array.isArray(resultContent)) {
      preview = truncate(extractText(resultContent), 200);
    }

    // Heuristic: success if no error flag and content doesn't start with "Error"
    let success: boolean | null = null;
    if (isError) {
      success = false;
    } else if (preview) {
      const lower = preview.toLowerCase();
      if (lower.includes("error") || lower.includes("failed") || lower.includes("exception")) {
        success = false;
      } else {
        success = true;
      }
    }

    return {
      id,
      timestamp,
      agent: "claude_code",
      sessionId,
      entryType: "tool_result",
      role: "tool",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: success,
      contentPreview: preview,
      tokenUsage: null,
    };
  }

  // Regular message (text)
  if (blockType === "text") {
    const text = extractText(content);
    return {
      id,
      timestamp,
      agent: "claude_code",
      sessionId,
      entryType: "message",
      role: entryType === "user" ? "user" : "assistant",
      toolName: null,
      toolInputSummary: null,
      toolSuccess: null,
      contentPreview: truncate(text, 200),
      tokenUsage,
    };
  }

  return null;
}
