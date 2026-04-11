/**
 * Cursor IDE SQLite parser.
 * Reads state.vscdb files and normalizes into the unified TraceEntry schema.
 */

import Database from "better-sqlite3";
import type { TraceEntry } from "../types";

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

const EMPTY_TRACE: Omit<TraceEntry, "id" | "timestamp" | "agent" | "sessionId" | "entryType" | "role" | "developer" | "machine" | "project"> = {
  model: null, tokenUsage: null, toolName: null, toolCallId: null,
  filePath: null, command: null, taskSummary: null,
  gitRepo: null, gitBranch: null, gitCommit: null,
  userPrompt: null, assistantText: null, thinking: null, reasoning: null, systemPrompt: null,
  toolResultContent: null, fileContent: null, stdout: null, queryData: null,
};

interface ComposerData {
  composerId: string;
  createdAt?: number;
  name?: string;
  isAgentic?: boolean;
  usageData?: Record<string, { costInCents?: number }>;
}

interface BubbleData {
  bubbleId: string;
  type: number;
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
 * Parse a Cursor state.vscdb file into TraceEntry array.
 */
export function parseCursorDb(
  dbPath: string,
  meta?: { developer?: string; machine?: string },
): TraceEntry[] {
  const db = new Database(dbPath, { readonly: true });
  const entries: TraceEntry[] = [];

  const tableCheck = db
    .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='cursorDiskKV'")
    .get();
  if (!tableCheck) { db.close(); return []; }

  const composerRows = db
    .prepare("SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'")
    .all() as { key: string; value: string }[];

  for (const row of composerRows) {
    let composer: ComposerData;
    try { composer = JSON.parse(row.value); } catch { continue; }

    const sessionId = composer.composerId;
    const timestamp = composer.createdAt ? new Date(composer.createdAt).toISOString() : "";

    // Extract model + cost from usageData
    let model: string | null = null;
    if (composer.usageData) {
      const firstModel = Object.keys(composer.usageData)[0];
      if (firstModel) model = firstModel;
    }

    const base = {
      ...EMPTY_TRACE,
      timestamp,
      agent: "cursor" as const,
      sessionId,
      model,
      developer: meta?.developer ?? "",
      machine: meta?.machine ?? "",
      project: "",
    };

    const bubbleRows = db
      .prepare("SELECT key, value FROM cursorDiskKV WHERE key LIKE ?")
      .all(`bubbleId:${sessionId}:%`) as { key: string; value: string }[];

    for (const bubbleRow of bubbleRows) {
      let bubble: BubbleData;
      try { bubble = JSON.parse(bubbleRow.value); } catch { continue; }

      const text = bubble.text ?? bubble.rawText ?? "";
      const tokenUsage = bubble.tokenCount?.inputTokens != null
        ? { input: bubble.tokenCount.inputTokens ?? 0, output: bubble.tokenCount.outputTokens ?? 0, cacheRead: 0, reasoning: 0 }
        : null;

      // Tool calls
      if (bubble.toolFormerData && bubble.toolFormerData.length > 0) {
        for (const tool of bubble.toolFormerData) {
          entries.push({
            ...base,
            id: `cur:${sessionId.slice(0, 8)}:${bubble.bubbleId}:${tool.toolName ?? "?"}`,
            entryType: "tool_call",
            role: "assistant",
            toolName: normalizeToolName(tool.toolName ?? "unknown"),
            filePath: tool.filePath ?? null,
            command: tool.command ?? null,
            tokenUsage,
          });
        }
        continue;
      }

      if (!text) continue;

      if (bubble.type === 1) {
        entries.push({
          ...base,
          id: `cur:${sessionId.slice(0, 8)}:${bubble.bubbleId}`,
          entryType: "message",
          role: "user",
          userPrompt: truncate(text, 500),
          tokenUsage,
        });
      } else {
        entries.push({
          ...base,
          id: `cur:${sessionId.slice(0, 8)}:${bubble.bubbleId}`,
          entryType: "message",
          role: "assistant",
          assistantText: truncate(text, 500),
          tokenUsage,
        });
      }
    }
  }

  db.close();
  return entries;
}

// Re-export for backward compat
export type NormalizedEntry = TraceEntry;
