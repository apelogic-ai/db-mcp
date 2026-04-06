import type { GatewayEvent, PrincipalType, PromptSource } from "./protocol.js";
import type { SessionLifecycleState, SessionParkedReason } from "./sessionLifecycle.js";
import { isSessionLifecycleState, isSessionParkedReason } from "./sessionLifecycle.js";
import type { SessionInterruption } from "./sessionInterruption.js";
import { isSessionInterruption } from "./sessionInterruption.js";

// State record types

export type OwnerIdentityStatus = "active" | "revoked";
export type PrincipalBindingStatus = "pending" | "verified" | "revoked";
export type PrincipalBindingProofFormat = "did-auth" | "vc" | "linked-domain" | "nexus-signed-binding";
export type PrincipalBindingSource = "web" | "telegram" | "tui" | "cli" | "api" | "gateway";

export interface OwnerIdentity {
  did: string;
  status: OwnerIdentityStatus;
  createdAt: string;
  updatedAt: string;
}

export interface PrincipalBindingRecord {
  principalType: PrincipalType;
  principalId: string;
  source: PrincipalBindingSource;
  ownerDid: string;
  bindingStatus: PrincipalBindingStatus;
  verificationMethodId?: string;
  proofFormat?: PrincipalBindingProofFormat;
  proofPayload?: string;
  createdAt: string;
  updatedAt: string;
}

export interface SessionRecord {
  id: string;
  workspaceId: string;
  ownerDid?: string;
  principalType: PrincipalType;
  principalId: string;
  source: PromptSource;
  displayName?: string;
  runtimeId: string;
  acpSessionId: string;
  status: "active" | "idle";
  lifecycleState?: SessionLifecycleState;
  parkedReason?: SessionParkedReason;
  parkedAt?: string;
  lifecycleUpdatedAt?: string;
  lifecycleVersion?: number;
  interruption?: SessionInterruption;
  createdAt: string;
  lastActivityAt: string;
  tokenUsage: { input: number; output: number };
  model: string;
}

export interface AuditEvent {
  id?: number;
  sessionId: string;
  timestamp: string;
  type: "tool_call" | "approval" | "deny" | "error";
  tool?: string;
  detail: string;
}

export interface StoredSessionEvent {
  id: number;
  sessionId: string;
  type: GatewayEvent["type"];
  payload: GatewayEvent;
  timestamp: string;
  executionId?: string;
  turnId?: string;
}

export type ExecutionState =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out";

export interface ExecutionRecord {
  id: string;
  sessionId: string;
  turnId: string;
  parentExecutionId?: string;
  idempotencyKey?: string;
  workspaceId: string;
  principalType: PrincipalType;
  principalId: string;
  source: PromptSource;
  runtimeId: string;
  model: string;
  policySnapshotId: string;
  state: ExecutionState;
  stopReason?: string;
  errorMessage?: string;
  createdAt: string;
  updatedAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface ChannelBindingRecord {
  adapterId: string;
  conversationId: string;
  sessionId: string;
  principalType: PrincipalType;
  principalId: string;
  runtimeId?: string;
  model?: string;
  workspaceId?: string;
  typingIndicator: boolean;
  streamingMode: "off" | "edit";
  steeringMode: "off" | "on";
  createdAt: string;
  updatedAt: string;
}

const SESSION_STATUSES = new Set(["active", "idle"]);
const OWNER_IDENTITY_STATUSES = new Set<OwnerIdentityStatus>(["active", "revoked"]);
const PRINCIPAL_BINDING_STATUSES = new Set<PrincipalBindingStatus>(["pending", "verified", "revoked"]);
const PRINCIPAL_BINDING_SOURCES = new Set<PrincipalBindingSource>(["web", "telegram", "tui", "cli", "api", "gateway"]);
const PRINCIPAL_BINDING_PROOF_FORMATS = new Set<PrincipalBindingProofFormat>([
  "did-auth",
  "vc",
  "linked-domain",
  "nexus-signed-binding",
]);
const AUDIT_TYPES = new Set(["tool_call", "approval", "deny", "error"]);
const EXECUTION_STATES = new Set<ExecutionState>([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
]);
const CHANNEL_STREAMING_MODES = new Set<ChannelBindingRecord["streamingMode"]>(["off", "edit"]);
const CHANNEL_STEERING_MODES = new Set<ChannelBindingRecord["steeringMode"]>(["off", "on"]);

export const isSessionRecord = (value: unknown): value is SessionRecord => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "string" &&
    typeof obj.workspaceId === "string" &&
    (obj.ownerDid === undefined || typeof obj.ownerDid === "string") &&
    (obj.principalType === "user" || obj.principalType === "service_account") &&
    typeof obj.principalId === "string" &&
    (obj.source === "interactive" || obj.source === "schedule" || obj.source === "hook" || obj.source === "api") &&
    (obj.displayName === undefined || typeof obj.displayName === "string") &&
    typeof obj.runtimeId === "string" &&
    typeof obj.acpSessionId === "string" &&
    typeof obj.status === "string" &&
    SESSION_STATUSES.has(obj.status) &&
    (obj.lifecycleState === undefined || isSessionLifecycleState(obj.lifecycleState)) &&
    (obj.parkedReason === undefined || isSessionParkedReason(obj.parkedReason)) &&
    (obj.parkedAt === undefined || typeof obj.parkedAt === "string") &&
    (obj.lifecycleUpdatedAt === undefined || typeof obj.lifecycleUpdatedAt === "string") &&
    (
      obj.lifecycleVersion === undefined
      || (
        typeof obj.lifecycleVersion === "number"
        && Number.isInteger(obj.lifecycleVersion)
        && obj.lifecycleVersion >= 0
      )
    ) &&
    (obj.interruption === undefined || isSessionInterruption(obj.interruption)) &&
    typeof obj.createdAt === "string" &&
    typeof obj.lastActivityAt === "string" &&
    typeof obj.model === "string" &&
    typeof obj.tokenUsage === "object" &&
    obj.tokenUsage !== null &&
    typeof (obj.tokenUsage as Record<string, unknown>).input === "number" &&
    typeof (obj.tokenUsage as Record<string, unknown>).output === "number"
  );
};

export const isOwnerIdentity = (value: unknown): value is OwnerIdentity => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.did === "string"
    && typeof obj.status === "string"
    && OWNER_IDENTITY_STATUSES.has(obj.status as OwnerIdentityStatus)
    && typeof obj.createdAt === "string"
    && typeof obj.updatedAt === "string"
  );
};

export const isPrincipalBindingRecord = (value: unknown): value is PrincipalBindingRecord => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    (obj.principalType === "user" || obj.principalType === "service_account")
    && typeof obj.principalId === "string"
    && typeof obj.source === "string"
    && PRINCIPAL_BINDING_SOURCES.has(obj.source as PrincipalBindingSource)
    && typeof obj.ownerDid === "string"
    && typeof obj.bindingStatus === "string"
    && PRINCIPAL_BINDING_STATUSES.has(obj.bindingStatus as PrincipalBindingStatus)
    && (obj.verificationMethodId === undefined || typeof obj.verificationMethodId === "string")
    && (obj.proofFormat === undefined || PRINCIPAL_BINDING_PROOF_FORMATS.has(obj.proofFormat as PrincipalBindingProofFormat))
    && (obj.proofPayload === undefined || typeof obj.proofPayload === "string")
    && typeof obj.createdAt === "string"
    && typeof obj.updatedAt === "string"
  );
};

export const isAuditEvent = (value: unknown): value is AuditEvent => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.sessionId === "string" &&
    typeof obj.timestamp === "string" &&
    typeof obj.type === "string" &&
    AUDIT_TYPES.has(obj.type) &&
    typeof obj.detail === "string"
  );
};

export const isExecutionRecord = (value: unknown): value is ExecutionRecord => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.id === "string" &&
    typeof obj.sessionId === "string" &&
    typeof obj.turnId === "string" &&
    (obj.parentExecutionId === undefined || typeof obj.parentExecutionId === "string") &&
    (obj.idempotencyKey === undefined || typeof obj.idempotencyKey === "string") &&
    typeof obj.workspaceId === "string" &&
    (obj.principalType === "user" || obj.principalType === "service_account") &&
    typeof obj.principalId === "string" &&
    (obj.source === "interactive" || obj.source === "schedule" || obj.source === "hook" || obj.source === "api") &&
    typeof obj.runtimeId === "string" &&
    typeof obj.model === "string" &&
    typeof obj.policySnapshotId === "string" &&
    typeof obj.state === "string" &&
    EXECUTION_STATES.has(obj.state as ExecutionState) &&
    (obj.stopReason === undefined || typeof obj.stopReason === "string") &&
    (obj.errorMessage === undefined || typeof obj.errorMessage === "string") &&
    typeof obj.createdAt === "string" &&
    typeof obj.updatedAt === "string" &&
    (obj.startedAt === undefined || typeof obj.startedAt === "string") &&
    (obj.completedAt === undefined || typeof obj.completedAt === "string")
  );
};

export const isChannelBindingRecord = (value: unknown): value is ChannelBindingRecord => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.adapterId === "string"
    && typeof obj.conversationId === "string"
    && typeof obj.sessionId === "string"
    && (obj.principalType === "user" || obj.principalType === "service_account")
    && typeof obj.principalId === "string"
    && (obj.runtimeId === undefined || typeof obj.runtimeId === "string")
    && (obj.model === undefined || typeof obj.model === "string")
    && (obj.workspaceId === undefined || typeof obj.workspaceId === "string")
    && typeof obj.typingIndicator === "boolean"
    && typeof obj.streamingMode === "string"
    && CHANNEL_STREAMING_MODES.has(obj.streamingMode as ChannelBindingRecord["streamingMode"])
    && typeof obj.steeringMode === "string"
    && CHANNEL_STEERING_MODES.has(obj.steeringMode as ChannelBindingRecord["steeringMode"])
    && typeof obj.createdAt === "string"
    && typeof obj.updatedAt === "string"
  );
};
