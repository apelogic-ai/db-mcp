/**
 * Cursor IDE SQLite parser.
 * Reads state.vscdb files and normalizes conversations into the unified schema.
 *
 * Cursor stores data in SQLite with a key-value schema:
 * - cursorDiskKV: composerData:<uuid> (sessions), bubbleId:<composerId>:<bubbleId> (messages)
 * - Bubble type 1 = user, type 2 = assistant
 * - Tool calls in toolFormerData array on assistant bubbles
 */

import Database from "better-sqlite3";

export interface NormalizedEntry {
  id: string;
  timestamp: string;
  agent: "cursor";
  sessionId: string;
  entryType: "message" | "tool_call" | "tool_result";
  role: "user" | "assistant" | "tool";
  toolName: string | null;
  toolInputSummary: string | null;
  toolSuccess: boolean | null;
  contentPreview: string | null;
  tokenUsage: { input: number; output: number; cacheRead: number } | null;
  isAgentic: boolean;
  sessionCost?: { cents: number; model: string };
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) : s;
}

const TOOL_NAME_MAP: Record<string, string> = {
  edit_file: "edit",
  terminal: "shell",
  read_file: "read",
  search_files: "search",
  list_directory: "list",
  file_search: "search",
  grep_search: "grep",
  codebase_search: "search",
  run_terminal_command: "shell",
};

function normalizeToolName(raw: string): string {
  return TOOL_NAME_MAP[raw] ?? raw;
}

interface ComposerData {
  composerId: string;
  createdAt?: number;
  name?: string;
  isAgentic?: boolean;
  usageData?: Record<string, { costInCents?: number; amount?: number }>;
}

interface BubbleData {
  bubbleId: string;
  type: number; // 1=user, 2=assistant
  text?: string;
  rawText?: string;
  tokenCount?: { inputTokens?: number; outputTokens?: number };
  toolFormerData?: Array<{
    toolName?: string;
    filePath?: string;
    command?: string;
    query?: string;
    status?: string;
  }>;
}

/**
 * Parse a Cursor state.vscdb file into normalized entries.
 */
export function parseCursorDb(dbPath: string): NormalizedEntry[] {
  const db = new Database(dbPath, { readonly: true });
  const entries: NormalizedEntry[] = [];

  // Check if cursorDiskKV table exists
  const tableCheck = db
    .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='cursorDiskKV'")
    .get();
  if (!tableCheck) {
    db.close();
    return [];
  }

  // Load all composer sessions
  const composerRows = db
    .prepare("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'")
    .all() as { key: string; value: string }[];

  for (const row of composerRows) {
    let composer: ComposerData;
    try {
      composer = JSON.parse(row.value) as ComposerData;
    } catch {
      continue;
    }

    const sessionId = composer.composerId;
    const isAgentic = composer.isAgentic ?? false;
    const timestamp = composer.createdAt
      ? new Date(composer.createdAt).toISOString()
      : "";

    // Extract cost from usageData
    let sessionCost: { cents: number; model: string } | undefined;
    if (composer.usageData) {
      for (const [model, usage] of Object.entries(composer.usageData)) {
        if (usage.costInCents) {
          sessionCost = { cents: usage.costInCents, model };
          break;
        }
      }
    }

    // Load bubbles for this session
    const bubbleRows = db
      .prepare("SELECT key, value FROM cursorDiskKV WHERE key LIKE ?")
      .all(`bubbleId:${sessionId}:%`) as { key: string; value: string }[];

    let isFirstEntry = true;

    for (const bubbleRow of bubbleRows) {
      let bubble: BubbleData;
      try {
        bubble = JSON.parse(bubbleRow.value) as BubbleData;
      } catch {
        continue;
      }

      const text = bubble.text ?? bubble.rawText ?? "";
      const tokenUsage =
        bubble.tokenCount?.inputTokens !== undefined
          ? {
              input: bubble.tokenCount.inputTokens ?? 0,
              output: bubble.tokenCount.outputTokens ?? 0,
              cacheRead: 0,
            }
          : null;

      // Tool calls from toolFormerData
      if (bubble.toolFormerData && bubble.toolFormerData.length > 0) {
        for (const tool of bubble.toolFormerData) {
          const rawName = tool.toolName ?? "unknown";
          const inputSummary =
            tool.filePath ?? tool.command ?? tool.query ?? null;

          const entry: NormalizedEntry = {
            id: `cur:${sessionId.slice(0, 8)}:${bubble.bubbleId}:tool:${rawName}`,
            timestamp,
            agent: "cursor",
            sessionId,
            entryType: "tool_call",
            role: "assistant",
            toolName: normalizeToolName(rawName),
            toolInputSummary: inputSummary
              ? truncate(inputSummary, 200)
              : null,
            toolSuccess:
              tool.status === "completed"
                ? true
                : tool.status === "failed"
                  ? false
                  : null,
            contentPreview: null,
            tokenUsage,
            isAgentic,
          };
          if (isFirstEntry && sessionCost) {
            entry.sessionCost = sessionCost;
            isFirstEntry = false;
          }
          entries.push(entry);
        }
        continue; // tool-only bubble, skip the text message
      }

      // Regular message
      if (!text) continue;

      const entry: NormalizedEntry = {
        id: `cur:${sessionId.slice(0, 8)}:${bubble.bubbleId}`,
        timestamp,
        agent: "cursor",
        sessionId,
        entryType: "message",
        role: bubble.type === 1 ? "user" : "assistant",
        toolName: null,
        toolInputSummary: null,
        toolSuccess: null,
        contentPreview: truncate(text, 200),
        tokenUsage,
        isAgentic,
      };
      if (isFirstEntry && sessionCost) {
        entry.sessionCost = sessionCost;
        isFirstEntry = false;
      }
      entries.push(entry);
    }
  }

  db.close();
  return entries;
}
