import type { StoredSessionEvent } from "./state.js";
// Client ↔ Gateway protocol types

import type { MemoryItem, TranscriptMessage } from "./memory.js";
import { isMemoryItem, isTranscriptMessage } from "./memory.js";
import type {
  SessionLifecycleEventRecord,
  SessionLifecycleEventType,
  SessionLifecycleState,
  SessionParkedReason,
} from "./sessionLifecycle.js";
import {
  isSessionLifecycleEventRecord,
  isSessionLifecycleEventType,
  isSessionLifecycleState,
  isSessionParkedReason,
} from "./sessionLifecycle.js";
import type { SessionInterruption } from "./sessionInterruption.js";
import { isSessionInterruption } from "./sessionInterruption.js";

export interface SessionInfo {
  id: string;
  status: "active" | "idle";
  lifecycleState?: SessionLifecycleState;
  parkedReason?: SessionParkedReason;
  parkedAt?: string;
  lifecycleUpdatedAt?: string;
  lifecycleVersion?: number;
  model: string;
  workspaceId?: string;
  ownerDid?: string;
  displayName?: string;
  interruption?: SessionInterruption;
  principalType?: PrincipalType;
  principalId?: string;
  source?: PromptSource;
  attachmentState?: SessionAttachmentState;
  createdAt: string;
  lastActivityAt: string;
}

export interface ApprovalOption {
  optionId: string;
  name: string;
  kind: string;
}

export type MemoryQueryAction = "stats" | "recent" | "search" | "context" | "clear";
export type MemoryScope = "session" | "workspace" | "hybrid";
export type UsageQueryAction = "summary" | "stats" | "recent" | "search" | "context" | "clear";
export type RuntimeHealthStatus = "starting" | "healthy" | "degraded" | "unavailable";
export type PrincipalType = "user" | "service_account";
export type PromptSource = "interactive" | "schedule" | "hook" | "api";
export type AuthAlgorithm = "ed25519";
export type SessionAttachmentState = "controller" | "elsewhere" | "detached";

export interface RuntimeHealthInfo {
  runtimeId: string;
  status: RuntimeHealthStatus;
  updatedAt: string;
  reason?: string;
}

export interface EventCorrelation {
  executionId?: string;
  parentExecutionId?: string;
  turnId?: string;
  policySnapshotId?: string;
}

export interface PromptImageInput {
  url: string;
  mediaType?: string;
}

export type ClientMessage =
  | {
      type: "prompt";
      sessionId: string;
      text: string;
      images?: PromptImageInput[];
      idempotencyKey?: string;
      parentExecutionId?: string;
    }
  | { type: "approval_response"; requestId: string; allow?: boolean; optionId?: string }
  | { type: "cancel"; sessionId: string }
  | { type: "session_close"; sessionId: string }
  | {
      type: "session_new";
      runtimeId?: string;
      model?: string;
      workspaceId?: string;
      principalType?: PrincipalType;
      principalId?: string;
      source?: PromptSource;
    }
  | {
      type: "session_list";
      limit?: number;
      cursor?: string;
    }
  | {
      type: "session_lifecycle_query";
      sessionId: string;
      limit?: number;
    }
  | {
      type: "session_rename";
      sessionId: string;
      displayName: string | null;
    }
  | { type: "session_replay"; sessionId: string }
  | { type: "session_attach"; sessionId: string }
  | { type: "session_detach"; sessionId?: string }
  | {
      type: "session_history";
      sessionId: string;
      afterId?: number;
      limit?: number;
    }
  | { type: "session_continue"; sessionId: string }
  | { type: "session_takeover"; sessionId: string }
  | {
      type: "auth_proof";
      principalType?: PrincipalType;
      principalId: string;
      publicKey: string;
      challengeId: string;
      nonce: string;
      signature: string;
      algorithm?: AuthAlgorithm;
    }
  | {
      type: "session_transfer_request";
      sessionId: string;
      targetPrincipalId: string;
      targetPrincipalType?: PrincipalType;
      expiresInMs?: number;
    }
  | {
      type: "session_transfer_accept";
      sessionId: string;
    }
  | {
      type: "session_transfer_dismiss";
      sessionId: string;
    }
  | {
      type: "memory_query";
      sessionId: string;
      action: MemoryQueryAction;
      query?: string;
      prompt?: string;
      limit?: number;
      scope?: MemoryScope;
    }
  | {
      type: "usage_query";
      sessionId: string;
      action?: UsageQueryAction;
      query?: string;
      prompt?: string;
      limit?: number;
      scope?: MemoryScope;
    };

export interface MemoryContextSnapshot {
  budgetTokens: number;
  totalTokens: number;
  hot: TranscriptMessage[];
  warm: MemoryItem[];
  cold: MemoryItem[];
  rendered: string;
}

export interface UsageMemoryStats {
  facts: number;
  summaries: number;
  total: number;
  transcriptMessages: number;
  memoryTokens: number;
  transcriptTokens: number;
}

export interface UsageSummary {
  tokens: {
    input: number;
    output: number;
    total: number;
  };
  executions: {
    total: number;
    queued: number;
    running: number;
    succeeded: number;
    failed: number;
    cancelled: number;
    timedOut: number;
  };
  memory?: {
    session: UsageMemoryStats;
    workspace: UsageMemoryStats;
  };
}

export type GatewayEvent =
  | ({ type: "text_delta"; sessionId: string; delta: string } & EventCorrelation)
  | ({ type: "thinking_delta"; sessionId: string; delta: string } & EventCorrelation)
  | ({ type: "tool_start"; sessionId: string; tool: string; toolCallId?: string; params: unknown } & EventCorrelation)
  | ({ type: "tool_end"; sessionId: string; tool: string; toolCallId?: string; result?: string } & EventCorrelation)
  | {
      type: "approval_request";
      sessionId: string;
      requestId: string;
      tool: string;
      description: string;
      options?: ApprovalOption[];
    } & EventCorrelation
  | ({ type: "turn_end"; sessionId: string; stopReason: string } & EventCorrelation)
  | ({ type: "error"; sessionId: string; message: string } & EventCorrelation)
  | {
      type: "session_created";
      sessionId: string;
      model: string;
      runtimeId?: string;
      workspaceId?: string;
      ownerDid?: string;
      displayName?: string;
      principalType?: PrincipalType;
      principalId?: string;
      source?: PromptSource;
      modelRouting?: Record<string, string>;
      modelAliases?: Record<string, string>;
      modelCatalog?: Record<string, string[]>;
      runtimeDefaults?: Record<string, string>;
    }
  | {
      type: "session_updated";
      sessionId: string;
      displayName: string | null;
      interruption?: SessionInterruption | null;
      lifecycleState?: SessionLifecycleState;
      parkedReason?: SessionParkedReason | null;
    }
  | {
      type: "session_invalidated";
      sessionId: string;
      reason: string;
      message: string;
    }
  | {
      type: "session_attached";
      sessionId: string;
      controller: boolean;
    }
  | {
      type: "session_detached";
      sessionId: string;
      reason: string;
    }
  | { type: "session_closed"; sessionId: string; reason: string }
  | {
      type: "auth_challenge";
      algorithm: AuthAlgorithm;
      challengeId: string;
      nonce: string;
      issuedAt: string;
      expiresAt: string;
    }
  | {
      type: "auth_result";
      ok: boolean;
      principalType?: PrincipalType;
      principalId?: string;
      ownerDid?: string;
      message?: string;
    }
  | {
      type: "session_transfer_requested";
      sessionId: string;
      fromPrincipalType: PrincipalType;
      fromPrincipalId: string;
      targetPrincipalType: PrincipalType;
      targetPrincipalId: string;
      expiresAt: string;
    }
  | {
      type: "session_transfer_updated";
      sessionId: string;
      fromPrincipalType: PrincipalType;
      fromPrincipalId: string;
      targetPrincipalType: PrincipalType;
      targetPrincipalId: string;
      state: "requested" | "accepted" | "dismissed" | "expired" | "cancelled";
      updatedAt: string;
      expiresAt?: string;
      reason?: string;
    }
  | {
      type: "session_transferred";
      sessionId: string;
      fromPrincipalType: PrincipalType;
      fromPrincipalId: string;
      targetPrincipalType: PrincipalType;
      targetPrincipalId: string;
      transferredAt: string;
    }
  | {
      type: "session_lifecycle";
      sessionId: string;
      eventType: SessionLifecycleEventType;
      fromState: SessionLifecycleState;
      toState: SessionLifecycleState;
      at: string;
      reason?: string;
      parkedReason?: SessionParkedReason;
      actorPrincipalType?: PrincipalType;
      actorPrincipalId?: string;
    }
  | {
      type: "session_lifecycle_result";
      sessionId: string;
      events: SessionLifecycleEventRecord[];
    }
  | { type: "runtime_health"; runtime: RuntimeHealthInfo }
  | {
      type: "session_history";
      sessionId: string;
      events: StoredSessionEvent[];
      hasMore: boolean;
      nextAfterId?: number;
    }
  | {
      type: "session_list";
      sessions: SessionInfo[];
      hasMore?: boolean;
      nextCursor?: string;
    }
  | { type: "transcript"; sessionId: string; messages: TranscriptMessage[] }
  | {
      type: "memory_result";
      sessionId: string;
      action: "stats";
      scope: Exclude<MemoryScope, "hybrid">;
      stats: {
        facts: number;
        summaries: number;
        total: number;
        transcriptMessages: number;
        memoryTokens: number;
        transcriptTokens: number;
      };
    }
  | {
      type: "memory_result";
      sessionId: string;
      action: "recent";
      scope: Exclude<MemoryScope, "hybrid">;
      limit: number;
      items: MemoryItem[];
    }
  | {
      type: "memory_result";
      sessionId: string;
      action: "search";
      scope: Exclude<MemoryScope, "hybrid">;
      query: string;
      limit: number;
      items: MemoryItem[];
    }
  | {
      type: "memory_result";
      sessionId: string;
      action: "context";
      scope: MemoryScope;
      prompt: string;
      context: MemoryContextSnapshot;
    }
  | {
      type: "memory_result";
      sessionId: string;
      action: "clear";
      scope: Exclude<MemoryScope, "hybrid">;
      deleted: number;
    }
  | {
      type: "usage_result";
      sessionId: string;
      action: "summary";
      summary: UsageSummary;
    }
  | {
      type: "usage_result";
      sessionId: string;
      action: "stats";
      scope: Exclude<MemoryScope, "hybrid">;
      stats: UsageMemoryStats;
    }
  | {
      type: "usage_result";
      sessionId: string;
      action: "recent";
      scope: Exclude<MemoryScope, "hybrid">;
      limit: number;
      items: MemoryItem[];
    }
  | {
      type: "usage_result";
      sessionId: string;
      action: "search";
      scope: Exclude<MemoryScope, "hybrid">;
      query: string;
      limit: number;
      items: MemoryItem[];
    }
  | {
      type: "usage_result";
      sessionId: string;
      action: "context";
      scope: MemoryScope;
      prompt: string;
      context: MemoryContextSnapshot;
    }
  | {
      type: "usage_result";
      sessionId: string;
      action: "clear";
      scope: Exclude<MemoryScope, "hybrid">;
      deleted: number;
    };

const CLIENT_MESSAGE_TYPES = new Set([
  "prompt",
  "approval_response",
  "cancel",
  "session_close",
  "session_new",
  "session_list",
  "session_lifecycle_query",
  "session_rename",
  "session_replay",
  "session_attach",
  "session_detach",
  "session_history",
  "session_continue",
  "session_takeover",
  "auth_proof",
  "session_transfer_request",
  "session_transfer_accept",
  "session_transfer_dismiss",
  "memory_query",
  "usage_query",
]);

const GATEWAY_EVENT_TYPES = new Set([
  "text_delta",
  "thinking_delta",
  "tool_start",
  "tool_end",
  "approval_request",
  "turn_end",
  "error",
  "session_created",
  "session_updated",
  "session_invalidated",
  "session_attached",
  "session_detached",
  "session_closed",
  "auth_challenge",
  "auth_result",
  "session_transfer_requested",
  "session_transfer_updated",
  "session_transferred",
  "session_lifecycle",
  "session_lifecycle_result",
  "runtime_health",
  "session_history",
  "session_list",
  "transcript",
  "memory_result",
  "usage_result",
]);

const MEMORY_QUERY_ACTIONS = new Set<MemoryQueryAction>([
  "stats",
  "recent",
  "search",
  "context",
  "clear",
]);

const SESSION_ATTACHMENT_STATES = new Set<SessionAttachmentState>([
  "controller",
  "elsewhere",
  "detached",
]);

const MEMORY_SCOPES = new Set<MemoryScope>([
  "session",
  "workspace",
  "hybrid",
]);

const USAGE_QUERY_ACTIONS = new Set<UsageQueryAction>([
  "summary",
  "stats",
  "recent",
  "search",
  "context",
  "clear",
]);

const PRINCIPAL_TYPES = new Set<PrincipalType>([
  "user",
  "service_account",
]);

const PROMPT_SOURCES = new Set<PromptSource>([
  "interactive",
  "schedule",
  "hook",
  "api",
]);

const isStringRecord = (value: unknown): value is Record<string, string> => (
  typeof value === "object"
  && value !== null
  && Object.values(value as Record<string, unknown>).every((v) => typeof v === "string")
);

const isStringArrayRecord = (value: unknown): value is Record<string, string[]> => (
  typeof value === "object"
  && value !== null
  && Object.values(value as Record<string, unknown>).every(
    (v) => Array.isArray(v) && v.every((item) => typeof item === "string"),
  )
);

const isMemoryContextSnapshot = (value: unknown): value is MemoryContextSnapshot => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.budgetTokens === "number"
    && typeof obj.totalTokens === "number"
    && typeof obj.rendered === "string"
    && Array.isArray(obj.hot)
    && obj.hot.every((entry) => isTranscriptMessage(entry))
    && Array.isArray(obj.warm)
    && obj.warm.every((entry) => isMemoryItem(entry))
    && Array.isArray(obj.cold)
    && obj.cold.every((entry) => isMemoryItem(entry))
  );
};

const hasValidCorrelation = (obj: Record<string, unknown>): boolean => (
  (obj.executionId === undefined || typeof obj.executionId === "string")
  && (obj.parentExecutionId === undefined || typeof obj.parentExecutionId === "string")
  && (obj.turnId === undefined || typeof obj.turnId === "string")
  && (obj.policySnapshotId === undefined || typeof obj.policySnapshotId === "string")
);

const isPromptImageInput = (value: unknown): value is PromptImageInput => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.url === "string"
    && obj.url.trim().length > 0
    && (obj.mediaType === undefined || typeof obj.mediaType === "string")
  );
};

const isStoredSessionEvent = (value: unknown): value is StoredSessionEvent => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "number"
    && Number.isInteger(obj.id)
    && typeof obj.sessionId === "string"
    && typeof obj.type === "string"
    && typeof obj.timestamp === "string"
    && (obj.executionId === undefined || typeof obj.executionId === "string")
    && (obj.turnId === undefined || typeof obj.turnId === "string")
    && isGatewayEvent(obj.payload)
  );
};

export const isClientMessage = (value: unknown): value is ClientMessage => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  if (typeof obj.type !== "string" || !CLIENT_MESSAGE_TYPES.has(obj.type)) return false;

  switch (obj.type) {
    case "prompt":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.text === "string"
        && (obj.images === undefined || (Array.isArray(obj.images) && obj.images.every((entry) => isPromptImageInput(entry))))
        && (obj.idempotencyKey === undefined || typeof obj.idempotencyKey === "string")
        && (obj.parentExecutionId === undefined || typeof obj.parentExecutionId === "string")
      );
    case "approval_response":
      return (
        typeof obj.requestId === "string" &&
        (typeof obj.allow === "boolean" || typeof obj.optionId === "string")
      );
    case "cancel":
      return typeof obj.sessionId === "string";
    case "session_close":
      return typeof obj.sessionId === "string";
    case "session_new":
      return (
        (obj.runtimeId === undefined || typeof obj.runtimeId === "string")
        && (obj.model === undefined || typeof obj.model === "string")
        && (obj.workspaceId === undefined || typeof obj.workspaceId === "string")
        && (obj.principalType === undefined || (typeof obj.principalType === "string" && PRINCIPAL_TYPES.has(obj.principalType as PrincipalType)))
        && (obj.principalId === undefined || typeof obj.principalId === "string")
        && (obj.source === undefined || (typeof obj.source === "string" && PROMPT_SOURCES.has(obj.source as PromptSource)))
      );
    case "session_list":
      return (
        (
          obj.limit === undefined
          || (typeof obj.limit === "number" && Number.isFinite(obj.limit) && obj.limit > 0)
        )
        && (obj.cursor === undefined || typeof obj.cursor === "string")
      );
    case "session_lifecycle_query":
      return (
        typeof obj.sessionId === "string"
        && (
          obj.limit === undefined
          || (typeof obj.limit === "number" && Number.isFinite(obj.limit) && obj.limit > 0)
        )
      );
    case "session_rename":
      return (
        typeof obj.sessionId === "string"
        && (obj.displayName === null || typeof obj.displayName === "string")
      );
    case "session_replay":
      return typeof obj.sessionId === "string";
    case "session_attach":
      return typeof obj.sessionId === "string";
    case "session_detach":
      return obj.sessionId === undefined || typeof obj.sessionId === "string";
    case "session_history":
      return (
        typeof obj.sessionId === "string"
        && (
          obj.afterId === undefined
          || (typeof obj.afterId === "number" && Number.isInteger(obj.afterId) && obj.afterId >= 0)
        )
        && (
          obj.limit === undefined
          || (typeof obj.limit === "number" && Number.isFinite(obj.limit) && obj.limit > 0)
        )
      );
    case "session_continue":
      return typeof obj.sessionId === "string";
    case "session_takeover":
      return typeof obj.sessionId === "string";
    case "auth_proof":
      return (
        typeof obj.principalId === "string"
        && typeof obj.publicKey === "string"
        && typeof obj.challengeId === "string"
        && typeof obj.nonce === "string"
        && typeof obj.signature === "string"
        && (obj.principalType === undefined || (typeof obj.principalType === "string" && PRINCIPAL_TYPES.has(obj.principalType as PrincipalType)))
        && (obj.algorithm === undefined || obj.algorithm === "ed25519")
      );
    case "session_transfer_request":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.targetPrincipalId === "string"
        && (obj.targetPrincipalType === undefined || (typeof obj.targetPrincipalType === "string" && PRINCIPAL_TYPES.has(obj.targetPrincipalType as PrincipalType)))
        && (
          obj.expiresInMs === undefined
          || (typeof obj.expiresInMs === "number" && Number.isFinite(obj.expiresInMs) && obj.expiresInMs > 0)
        )
      );
    case "session_transfer_accept":
      return typeof obj.sessionId === "string";
    case "session_transfer_dismiss":
      return typeof obj.sessionId === "string";
    case "memory_query":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.action === "string"
        && MEMORY_QUERY_ACTIONS.has(obj.action as MemoryQueryAction)
        && (obj.query === undefined || typeof obj.query === "string")
        && (obj.prompt === undefined || typeof obj.prompt === "string")
        && (
          obj.limit === undefined
          || (typeof obj.limit === "number" && Number.isFinite(obj.limit) && obj.limit > 0)
        )
        && (obj.scope === undefined || (typeof obj.scope === "string" && MEMORY_SCOPES.has(obj.scope as MemoryScope)))
      );
    case "usage_query":
      return (
        typeof obj.sessionId === "string"
        && (
          obj.action === undefined
          || (typeof obj.action === "string" && USAGE_QUERY_ACTIONS.has(obj.action as UsageQueryAction))
        )
        && (obj.query === undefined || typeof obj.query === "string")
        && (obj.prompt === undefined || typeof obj.prompt === "string")
        && (
          obj.limit === undefined
          || (typeof obj.limit === "number" && Number.isFinite(obj.limit) && obj.limit > 0)
        )
        && (obj.scope === undefined || (typeof obj.scope === "string" && MEMORY_SCOPES.has(obj.scope as MemoryScope)))
      );
    default:
      return false;
  }
};

export const isGatewayEvent = (value: unknown): value is GatewayEvent => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  if (typeof obj.type !== "string" || !GATEWAY_EVENT_TYPES.has(obj.type)) return false;

  switch (obj.type) {
    case "text_delta":
    case "thinking_delta":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.delta === "string"
        && hasValidCorrelation(obj)
      );
    case "tool_start":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.tool === "string"
        && hasValidCorrelation(obj)
      );
    case "tool_end":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.tool === "string"
        && hasValidCorrelation(obj)
      );
    case "approval_request":
      return (
        typeof obj.sessionId === "string" &&
        typeof obj.requestId === "string" &&
        typeof obj.tool === "string" &&
        typeof obj.description === "string" &&
        (
          obj.options === undefined
          || (
            Array.isArray(obj.options)
            && obj.options.every(
              (opt) => (
                typeof opt === "object"
                && opt !== null
                && typeof (opt as Record<string, unknown>).optionId === "string"
                && typeof (opt as Record<string, unknown>).name === "string"
                && typeof (opt as Record<string, unknown>).kind === "string"
              ),
            )
          )
        )
        && hasValidCorrelation(obj)
      );
    case "turn_end":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.stopReason === "string"
        && hasValidCorrelation(obj)
      );
    case "error":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.message === "string"
        && hasValidCorrelation(obj)
      );
    case "session_created":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.model === "string"
        && (obj.runtimeId === undefined || typeof obj.runtimeId === "string")
        && (obj.workspaceId === undefined || typeof obj.workspaceId === "string")
        && (obj.ownerDid === undefined || typeof obj.ownerDid === "string")
        && (obj.displayName === undefined || typeof obj.displayName === "string")
        && (obj.principalType === undefined || (typeof obj.principalType === "string" && PRINCIPAL_TYPES.has(obj.principalType as PrincipalType)))
        && (obj.principalId === undefined || typeof obj.principalId === "string")
        && (obj.source === undefined || (typeof obj.source === "string" && PROMPT_SOURCES.has(obj.source as PromptSource)))
        && (obj.modelRouting === undefined || isStringRecord(obj.modelRouting))
        && (obj.modelAliases === undefined || isStringRecord(obj.modelAliases))
        && (obj.modelCatalog === undefined || isStringArrayRecord(obj.modelCatalog))
        && (obj.runtimeDefaults === undefined || isStringRecord(obj.runtimeDefaults))
      );
    case "session_updated":
      return (
        typeof obj.sessionId === "string"
        && (obj.displayName === null || typeof obj.displayName === "string")
        && (obj.interruption === undefined || obj.interruption === null || isSessionInterruption(obj.interruption))
        && (obj.lifecycleState === undefined || isSessionLifecycleState(obj.lifecycleState))
        && (obj.parkedReason === undefined || obj.parkedReason === null || isSessionParkedReason(obj.parkedReason))
      );
    case "session_invalidated":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.reason === "string"
        && typeof obj.message === "string"
      );
    case "session_attached":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.controller === "boolean"
      );
    case "session_detached":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.reason === "string"
      );
    case "session_closed":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.reason === "string"
      );
    case "auth_challenge":
      return (
        obj.algorithm === "ed25519"
        && typeof obj.challengeId === "string"
        && typeof obj.nonce === "string"
        && typeof obj.issuedAt === "string"
        && typeof obj.expiresAt === "string"
      );
    case "auth_result":
      return (
        typeof obj.ok === "boolean"
        && (obj.principalType === undefined || (typeof obj.principalType === "string" && PRINCIPAL_TYPES.has(obj.principalType as PrincipalType)))
        && (obj.principalId === undefined || typeof obj.principalId === "string")
        && (obj.ownerDid === undefined || typeof obj.ownerDid === "string")
        && (obj.message === undefined || typeof obj.message === "string")
      );
    case "session_transfer_requested":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.fromPrincipalType === "string"
        && PRINCIPAL_TYPES.has(obj.fromPrincipalType as PrincipalType)
        && typeof obj.fromPrincipalId === "string"
        && typeof obj.targetPrincipalType === "string"
        && PRINCIPAL_TYPES.has(obj.targetPrincipalType as PrincipalType)
        && typeof obj.targetPrincipalId === "string"
        && typeof obj.expiresAt === "string"
      );
    case "session_transfer_updated":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.fromPrincipalType === "string"
        && PRINCIPAL_TYPES.has(obj.fromPrincipalType as PrincipalType)
        && typeof obj.fromPrincipalId === "string"
        && typeof obj.targetPrincipalType === "string"
        && PRINCIPAL_TYPES.has(obj.targetPrincipalType as PrincipalType)
        && typeof obj.targetPrincipalId === "string"
        && typeof obj.state === "string"
        && (
          obj.state === "requested"
          || obj.state === "accepted"
          || obj.state === "dismissed"
          || obj.state === "expired"
          || obj.state === "cancelled"
        )
        && typeof obj.updatedAt === "string"
        && (obj.expiresAt === undefined || typeof obj.expiresAt === "string")
        && (obj.reason === undefined || typeof obj.reason === "string")
      );
    case "session_transferred":
      return (
        typeof obj.sessionId === "string"
        && typeof obj.fromPrincipalType === "string"
        && PRINCIPAL_TYPES.has(obj.fromPrincipalType as PrincipalType)
        && typeof obj.fromPrincipalId === "string"
        && typeof obj.targetPrincipalType === "string"
        && PRINCIPAL_TYPES.has(obj.targetPrincipalType as PrincipalType)
        && typeof obj.targetPrincipalId === "string"
        && typeof obj.transferredAt === "string"
      );
    case "session_lifecycle":
      return (
        typeof obj.sessionId === "string"
        && isSessionLifecycleEventType(obj.eventType)
        && isSessionLifecycleState(obj.fromState)
        && isSessionLifecycleState(obj.toState)
        && typeof obj.at === "string"
        && (obj.reason === undefined || typeof obj.reason === "string")
        && (obj.parkedReason === undefined || isSessionParkedReason(obj.parkedReason))
        && (obj.actorPrincipalType === undefined || (typeof obj.actorPrincipalType === "string" && PRINCIPAL_TYPES.has(obj.actorPrincipalType as PrincipalType)))
        && (obj.actorPrincipalId === undefined || typeof obj.actorPrincipalId === "string")
      );
    case "session_lifecycle_result":
      return (
        typeof obj.sessionId === "string"
        && Array.isArray(obj.events)
        && obj.events.every((event) => isSessionLifecycleEventRecord(event))
      );
    case "runtime_health":
      return (
        typeof obj.runtime === "object"
        && obj.runtime !== null
        && typeof (obj.runtime as Record<string, unknown>).runtimeId === "string"
        && typeof (obj.runtime as Record<string, unknown>).status === "string"
        && (
          (obj.runtime as Record<string, unknown>).status === "starting"
          || (obj.runtime as Record<string, unknown>).status === "healthy"
          || (obj.runtime as Record<string, unknown>).status === "degraded"
          || (obj.runtime as Record<string, unknown>).status === "unavailable"
        )
        && typeof (obj.runtime as Record<string, unknown>).updatedAt === "string"
        && (
          (obj.runtime as Record<string, unknown>).reason === undefined
          || typeof (obj.runtime as Record<string, unknown>).reason === "string"
        )
      );
    case "session_history":
      return (
        typeof obj.sessionId === "string"
        && Array.isArray(obj.events)
        && obj.events.every((event) => isStoredSessionEvent(event))
        && typeof obj.hasMore === "boolean"
        && (obj.nextAfterId === undefined || (typeof obj.nextAfterId === "number" && Number.isInteger(obj.nextAfterId) && obj.nextAfterId >= 0))
      );
    case "session_list":
      return (
        Array.isArray(obj.sessions)
        && obj.sessions.every((entry) => (
          typeof entry === "object"
          && entry !== null
          && typeof (entry as Record<string, unknown>).id === "string"
          && typeof (entry as Record<string, unknown>).status === "string"
          && (
            (entry as Record<string, unknown>).status === "active"
            || (entry as Record<string, unknown>).status === "idle"
          )
          && typeof (entry as Record<string, unknown>).model === "string"
          && ((entry as Record<string, unknown>).ownerDid === undefined || typeof (entry as Record<string, unknown>).ownerDid === "string")
          && ((entry as Record<string, unknown>).lifecycleState === undefined || isSessionLifecycleState((entry as Record<string, unknown>).lifecycleState))
          && ((entry as Record<string, unknown>).parkedReason === undefined || isSessionParkedReason((entry as Record<string, unknown>).parkedReason))
          && ((entry as Record<string, unknown>).parkedAt === undefined || typeof (entry as Record<string, unknown>).parkedAt === "string")
          && ((entry as Record<string, unknown>).lifecycleUpdatedAt === undefined || typeof (entry as Record<string, unknown>).lifecycleUpdatedAt === "string")
          && ((entry as Record<string, unknown>).lifecycleVersion === undefined || typeof (entry as Record<string, unknown>).lifecycleVersion === "number")
          && ((entry as Record<string, unknown>).workspaceId === undefined || typeof (entry as Record<string, unknown>).workspaceId === "string")
          && ((entry as Record<string, unknown>).displayName === undefined || typeof (entry as Record<string, unknown>).displayName === "string")
          && ((entry as Record<string, unknown>).interruption === undefined || isSessionInterruption((entry as Record<string, unknown>).interruption))
          && ((entry as Record<string, unknown>).principalType === undefined || PRINCIPAL_TYPES.has((entry as Record<string, unknown>).principalType as PrincipalType))
          && ((entry as Record<string, unknown>).principalId === undefined || typeof (entry as Record<string, unknown>).principalId === "string")
          && ((entry as Record<string, unknown>).source === undefined || PROMPT_SOURCES.has((entry as Record<string, unknown>).source as PromptSource))
          && ((entry as Record<string, unknown>).attachmentState === undefined || SESSION_ATTACHMENT_STATES.has((entry as Record<string, unknown>).attachmentState as SessionAttachmentState))
          && typeof (entry as Record<string, unknown>).createdAt === "string"
          && typeof (entry as Record<string, unknown>).lastActivityAt === "string"
        ))
        && (obj.hasMore === undefined || typeof obj.hasMore === "boolean")
        && (obj.nextCursor === undefined || typeof obj.nextCursor === "string")
      );
    case "transcript":
      return (
        typeof obj.sessionId === "string"
        && Array.isArray(obj.messages)
        && obj.messages.every((message) => isTranscriptMessage(message))
      );
    case "memory_result":
      if (typeof obj.sessionId !== "string" || typeof obj.action !== "string") return false;
      switch (obj.action) {
        case "stats":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.stats === "object"
            && obj.stats !== null
            && typeof (obj.stats as Record<string, unknown>).facts === "number"
            && typeof (obj.stats as Record<string, unknown>).summaries === "number"
            && typeof (obj.stats as Record<string, unknown>).total === "number"
            && typeof (obj.stats as Record<string, unknown>).transcriptMessages === "number"
            && typeof (obj.stats as Record<string, unknown>).memoryTokens === "number"
            && typeof (obj.stats as Record<string, unknown>).transcriptTokens === "number"
          );
        case "recent":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.limit === "number"
            && Array.isArray(obj.items)
            && obj.items.every((item) => isMemoryItem(item))
          );
        case "search":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.query === "string"
            && typeof obj.limit === "number"
            && Array.isArray(obj.items)
            && obj.items.every((item) => isMemoryItem(item))
          );
        case "context":
          return (
            typeof obj.scope === "string"
            && MEMORY_SCOPES.has(obj.scope as MemoryScope)
            && typeof obj.prompt === "string"
            && isMemoryContextSnapshot(obj.context)
          );
        case "clear":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.deleted === "number"
          );
        default:
          return false;
      }
    case "usage_result":
      if (typeof obj.sessionId !== "string" || typeof obj.action !== "string") return false;
      switch (obj.action) {
        case "summary":
          return (
            typeof obj.summary === "object"
            && obj.summary !== null
            && typeof (obj.summary as Record<string, unknown>).tokens === "object"
            && (obj.summary as Record<string, unknown>).tokens !== null
            && typeof ((obj.summary as Record<string, unknown>).tokens as Record<string, unknown>).input === "number"
            && typeof ((obj.summary as Record<string, unknown>).tokens as Record<string, unknown>).output === "number"
            && typeof ((obj.summary as Record<string, unknown>).tokens as Record<string, unknown>).total === "number"
            && typeof (obj.summary as Record<string, unknown>).executions === "object"
            && (obj.summary as Record<string, unknown>).executions !== null
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).total === "number"
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).queued === "number"
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).running === "number"
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).succeeded === "number"
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).failed === "number"
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).cancelled === "number"
            && typeof ((obj.summary as Record<string, unknown>).executions as Record<string, unknown>).timedOut === "number"
            && (
              (obj.summary as Record<string, unknown>).memory === undefined
              || (
                typeof (obj.summary as Record<string, unknown>).memory === "object"
                && (obj.summary as Record<string, unknown>).memory !== null
                && typeof ((obj.summary as Record<string, unknown>).memory as Record<string, unknown>).session === "object"
                && typeof ((obj.summary as Record<string, unknown>).memory as Record<string, unknown>).workspace === "object"
              )
            )
          );
        case "stats":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.stats === "object"
            && obj.stats !== null
            && typeof (obj.stats as Record<string, unknown>).facts === "number"
            && typeof (obj.stats as Record<string, unknown>).summaries === "number"
            && typeof (obj.stats as Record<string, unknown>).total === "number"
            && typeof (obj.stats as Record<string, unknown>).transcriptMessages === "number"
            && typeof (obj.stats as Record<string, unknown>).memoryTokens === "number"
            && typeof (obj.stats as Record<string, unknown>).transcriptTokens === "number"
          );
        case "recent":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.limit === "number"
            && Array.isArray(obj.items)
            && obj.items.every((item) => isMemoryItem(item))
          );
        case "search":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.query === "string"
            && typeof obj.limit === "number"
            && Array.isArray(obj.items)
            && obj.items.every((item) => isMemoryItem(item))
          );
        case "context":
          return (
            typeof obj.scope === "string"
            && MEMORY_SCOPES.has(obj.scope as MemoryScope)
            && typeof obj.prompt === "string"
            && isMemoryContextSnapshot(obj.context)
          );
        case "clear":
          return (
            typeof obj.scope === "string"
            && (obj.scope === "session" || obj.scope === "workspace")
            && typeof obj.deleted === "number"
          );
        default:
          return false;
      }
    default:
      return false;
  }
};

export const parseClientMessage = (json: string): ClientMessage => {
  const parsed = JSON.parse(json);
  if (!isClientMessage(parsed)) {
    throw new Error(`Invalid client message: ${json}`);
  }
  return parsed;
};
