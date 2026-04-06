// Transcript and memory types

export type MessageRole = "user" | "assistant" | "tool" | "system";
export type MemoryItemKind = "fact" | "summary";

export interface TranscriptMessage {
  id: number;
  sessionId: string;
  role: MessageRole;
  content: string;
  toolName?: string;
  toolCallId?: string;
  timestamp: string;
  tokenEstimate: number;
}

export interface MemoryItem {
  id: number;
  sessionId: string;
  kind: MemoryItemKind;
  content: string;
  source: string;
  confidence: number;
  keywords: string[];
  createdAt: string;
  lastAccessedAt: string;
  tokenEstimate: number;
}

const MESSAGE_ROLES = new Set(["user", "assistant", "tool", "system"]);
const MEMORY_ITEM_KINDS = new Set(["fact", "summary"]);

export const isTranscriptMessage = (value: unknown): value is TranscriptMessage => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "number" &&
    typeof obj.sessionId === "string" &&
    typeof obj.role === "string" &&
    MESSAGE_ROLES.has(obj.role) &&
    typeof obj.content === "string" &&
    typeof obj.timestamp === "string" &&
    typeof obj.tokenEstimate === "number" &&
    (obj.toolName === undefined || typeof obj.toolName === "string") &&
    (obj.toolCallId === undefined || typeof obj.toolCallId === "string")
  );
};

export const isMemoryItem = (value: unknown): value is MemoryItem => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "number"
    && typeof obj.sessionId === "string"
    && typeof obj.kind === "string"
    && MEMORY_ITEM_KINDS.has(obj.kind)
    && typeof obj.content === "string"
    && typeof obj.source === "string"
    && typeof obj.confidence === "number"
    && Number.isFinite(obj.confidence)
    && obj.confidence >= 0
    && obj.confidence <= 1
    && Array.isArray(obj.keywords)
    && obj.keywords.every((keyword) => typeof keyword === "string")
    && typeof obj.createdAt === "string"
    && typeof obj.lastAccessedAt === "string"
    && typeof obj.tokenEstimate === "number"
  );
};

/** Rough token estimate: ~4 chars per token for English text. */
export const estimateTokens = (text: string): number => Math.ceil(text.length / 4);
