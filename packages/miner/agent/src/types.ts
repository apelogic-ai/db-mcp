/**
 * Unified trace entry schema with sensitivity classification.
 *
 * Every field is tagged by sensitivity level:
 *   SAFE      — metadata, ship freely
 *   MODERATE  — behavioral, ship with care
 *   SENSITIVE — content, opt-in only
 *   HIGH_RISK — data/PII, never ships
 */

import { createHash } from "node:crypto";

// ---------------------------------------------------------------------------
// Disclosure levels
// ---------------------------------------------------------------------------

export type DisclosureLevel = "basic" | "moderate" | "sensitive";

// ---------------------------------------------------------------------------
// Unified trace entry — all agents normalize into this
// ---------------------------------------------------------------------------

export interface TraceEntry {
  // --- SAFE (metadata) ---
  id: string;
  timestamp: string;
  agent: "claude_code" | "codex" | "cursor";
  sessionId: string;
  entryType: "message" | "tool_call" | "tool_result" | "reasoning" | "task_summary";
  role: "user" | "assistant" | "system" | "tool";
  model: string | null;
  tokenUsage: {
    input: number;
    output: number;
    cacheRead: number;
    reasoning: number;
  } | null;
  developer: string;
  machine: string;
  project: string;

  // --- MODERATE (behavioral) ---
  toolName: string | null;
  toolCallId: string | null;
  filePath: string | null;
  command: string | null;
  taskSummary: string | null;
  gitRepo: string | null;
  gitBranch: string | null;
  gitCommit: string | null;

  // --- SENSITIVE (content) ---
  userPrompt: string | null;
  assistantText: string | null;
  thinking: string | null;
  reasoning: string | null;
  systemPrompt: string | null;

  // --- HIGH RISK (data) — never shipped ---
  toolResultContent: string | null;
  fileContent: string | null;
  stdout: string | null;
  queryData: string | null;
}

// ---------------------------------------------------------------------------
// Per-vendor raw entry types (what the JSONL actually contains)
// ---------------------------------------------------------------------------

/** Claude Code raw JSONL entry */
export interface ClaudeCodeRawEntry {
  type: "user" | "assistant" | "queue-operation";
  timestamp: string;
  message?: {
    id?: string;
    model?: string;
    role?: string;
    stop_reason?: string;
    content?: Array<{
      type: string;
      text?: string;
      thinking?: string;
      name?: string;
      id?: string;
      input?: Record<string, unknown>;
      content?: string | Array<{ type: string; text?: string }>;
      tool_use_id?: string;
      is_error?: boolean;
      signature?: string;
    }>;
    usage?: {
      input_tokens?: number;
      output_tokens?: number;
      cache_read_input_tokens?: number;
      cache_creation_input_tokens?: number;
    };
  };
  cwd?: string;
  sessionId?: string;
  gitBranch?: string;
  version?: string;
  entrypoint?: string;
  uuid?: string;
  parentUuid?: string;
  toolUseResult?: {
    stdout?: string;
    stderr?: string;
    file?: { content?: string; filePath?: string };
    type?: string;
  };
}

/** Codex raw JSONL entry */
export interface CodexRawEntry {
  type: "session_meta" | "response_item" | "event_msg" | "turn_context";
  timestamp: string;
  payload: {
    type?: string;
    id?: string;
    name?: string;
    call_id?: string;
    arguments?: string;
    input?: string;
    output?: string;
    result?: string;
    role?: string;
    message?: string;
    content?: Array<{ type: string; text?: string; value?: string }>;
    last_agent_message?: string;
    status?: string;
    turn_id?: string;
    model?: string;
    model_provider?: string;
    cwd?: string;
    cli_version?: string;
    source?: string;
    originator?: string;
    effort?: string;
    encrypted_content?: string;
    base_instructions?: { text?: string };
    user_instructions?: string;
    developer_instructions?: string;
    git?: { branch?: string; commit_hash?: string; repository_url?: string };
    info?: {
      last_token_usage?: {
        input_tokens?: number;
        output_tokens?: number;
        cached_input_tokens?: number;
        reasoning_output_tokens?: number;
        total_tokens?: number;
      };
    };
    rate_limits?: Record<string, unknown>;
  };
}

/** Cursor raw bubble (from SQLite cursorDiskKV) */
export interface CursorRawBubble {
  _v: number;
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

// ---------------------------------------------------------------------------
// Disclosure filter — strips fields based on configured level
// ---------------------------------------------------------------------------

const MODERATE_FIELDS: (keyof TraceEntry)[] = [
  "toolCallId", "filePath", "command", "taskSummary",
  "gitRepo", "gitBranch", "gitCommit",
];

const SENSITIVE_FIELDS: (keyof TraceEntry)[] = [
  "userPrompt", "assistantText", "thinking", "reasoning", "systemPrompt",
];

const HIGH_RISK_FIELDS: (keyof TraceEntry)[] = [
  "toolResultContent", "fileContent", "stdout", "queryData",
];

/**
 * Apply disclosure level — strip fields above the allowed tier.
 * HIGH RISK is always stripped regardless of level.
 */
export function applyDisclosure(
  entry: TraceEntry,
  level: DisclosureLevel,
): TraceEntry {
  const result = { ...entry };

  // HIGH RISK — always stripped
  for (const field of HIGH_RISK_FIELDS) {
    (result as Record<string, unknown>)[field] = null;
  }

  // SENSITIVE — stripped unless level is "sensitive"
  if (level !== "sensitive") {
    for (const field of SENSITIVE_FIELDS) {
      (result as Record<string, unknown>)[field] = null;
    }
  }

  // MODERATE — stripped if level is "basic"
  if (level === "basic") {
    for (const field of MODERATE_FIELDS) {
      (result as Record<string, unknown>)[field] = null;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Anonymization — replace identity with deterministic hashes
// ---------------------------------------------------------------------------

function anonHash(value: string): string {
  return "anon:" + createHash("sha256").update(value).digest("hex").slice(0, 12);
}

/**
 * Replace developer and machine with deterministic hashes.
 * Same input always produces same hash (enables cross-correlation).
 */
export function anonymizeEntry(entry: TraceEntry): TraceEntry {
  return {
    ...entry,
    developer: anonHash(entry.developer),
    machine: anonHash(entry.machine),
  };
}
