import type { PrincipalType } from "./protocol.js";

export type SessionLifecycleState = "live" | "parked" | "closed";

export type SessionParkedReason =
  | "transfer_pending"
  | "transfer_expired"
  | "runtime_timeout"
  | "idle"
  | "owner_disconnected"
  | "approval_pending"
  | "manual";

export type SessionLifecycleEventType =
  | "SESSION_CREATED"
  | "APPROVAL_REQUESTED"
  | "APPROVAL_RESOLVED"
  | "TRANSFER_REQUESTED"
  | "TRANSFER_ACCEPTED"
  | "TRANSFER_DISMISSED"
  | "TRANSFER_EXPIRED"
  | "OWNER_RESUMED"
  | "TAKEOVER"
  | "RUNTIME_TIMEOUT"
  | "IDLE_TIMEOUT"
  | "OWNER_DISCONNECTED"
  | "SESSION_CLOSED";

export interface SessionLifecycleEventRecord {
  id?: number;
  sessionId: string;
  eventType: SessionLifecycleEventType;
  fromState: SessionLifecycleState;
  toState: SessionLifecycleState;
  reason?: string;
  parkedReason?: SessionParkedReason;
  actorPrincipalType?: PrincipalType;
  actorPrincipalId?: string;
  metadata?: string;
  createdAt: string;
}

export interface SessionLifecycleTransitionResult {
  fromState: SessionLifecycleState;
  toState: SessionLifecycleState;
  eventType: SessionLifecycleEventType;
  parkedReason?: SessionParkedReason;
}

export const TRANSFER_ACCEPT_ALLOWED_PARKED_REASONS = [
  "transfer_pending",
] as const satisfies readonly SessionParkedReason[];

export const TRANSFER_DISMISS_ALLOWED_PARKED_REASONS = [
  "transfer_pending",
  "transfer_expired",
] as const satisfies readonly SessionParkedReason[];

export const OWNER_TRANSFER_RESUME_ALLOWED_PARKED_REASONS = [
  "transfer_pending",
  "transfer_expired",
] as const satisfies readonly SessionParkedReason[];

export const OWNER_RESUMABLE_PARKED_REASONS = [
  "owner_disconnected",
  "runtime_timeout",
  "idle",
  "manual",
  "transfer_expired",
] as const satisfies readonly SessionParkedReason[];

export const AUTO_RESUME_ALLOWED_PARKED_REASONS = [
  "owner_disconnected",
  "runtime_timeout",
  "idle",
  "manual",
  "transfer_expired",
  "approval_pending",
] as const satisfies readonly SessionParkedReason[];

export const TAKEOVER_ALLOWED_PARKED_REASONS = [
  "owner_disconnected",
  "runtime_timeout",
  "idle",
  "manual",
  "transfer_expired",
] as const satisfies readonly SessionParkedReason[];

const OWNER_RESUMABLE_PARKED_REASON_SET = new Set<SessionParkedReason>(OWNER_RESUMABLE_PARKED_REASONS);
const TAKEOVER_ALLOWED_PARKED_REASON_SET = new Set<SessionParkedReason>(TAKEOVER_ALLOWED_PARKED_REASONS);
const AUTO_RESUME_ALLOWED_PARKED_REASON_SET = new Set<SessionParkedReason>(AUTO_RESUME_ALLOWED_PARKED_REASONS);

const SESSION_LIFECYCLE_STATES = new Set<SessionLifecycleState>([
  "live",
  "parked",
  "closed",
]);

const SESSION_PARKED_REASONS = new Set<SessionParkedReason>([
  "transfer_pending",
  "transfer_expired",
  "runtime_timeout",
  "idle",
  "owner_disconnected",
  "approval_pending",
  "manual",
]);

const SESSION_LIFECYCLE_EVENT_TYPES = new Set<SessionLifecycleEventType>([
  "SESSION_CREATED",
  "APPROVAL_REQUESTED",
  "APPROVAL_RESOLVED",
  "TRANSFER_REQUESTED",
  "TRANSFER_ACCEPTED",
  "TRANSFER_DISMISSED",
  "TRANSFER_EXPIRED",
  "OWNER_RESUMED",
  "TAKEOVER",
  "RUNTIME_TIMEOUT",
  "IDLE_TIMEOUT",
  "OWNER_DISCONNECTED",
  "SESSION_CLOSED",
]);

const SESSION_LIFECYCLE_TRANSITIONS: Record<SessionLifecycleState, Partial<Record<SessionLifecycleEventType, SessionLifecycleState>>> = {
  live: {
    SESSION_CREATED: "live",
    APPROVAL_REQUESTED: "parked",
    TRANSFER_REQUESTED: "parked",
    RUNTIME_TIMEOUT: "parked",
    IDLE_TIMEOUT: "parked",
    OWNER_DISCONNECTED: "parked",
    SESSION_CLOSED: "closed",
  },
  parked: {
    APPROVAL_REQUESTED: "parked",
    APPROVAL_RESOLVED: "live",
    TRANSFER_REQUESTED: "parked",
    TRANSFER_ACCEPTED: "live",
    TRANSFER_DISMISSED: "live",
    TRANSFER_EXPIRED: "parked",
    OWNER_RESUMED: "live",
    TAKEOVER: "live",
    RUNTIME_TIMEOUT: "parked",
    IDLE_TIMEOUT: "parked",
    OWNER_DISCONNECTED: "parked",
    SESSION_CLOSED: "closed",
  },
  closed: {},
};

const DEFAULT_PARKED_REASON_BY_EVENT: Partial<Record<SessionLifecycleEventType, SessionParkedReason>> = {
  TRANSFER_REQUESTED: "transfer_pending",
  TRANSFER_EXPIRED: "transfer_expired",
  RUNTIME_TIMEOUT: "runtime_timeout",
  IDLE_TIMEOUT: "idle",
  OWNER_DISCONNECTED: "owner_disconnected",
  APPROVAL_REQUESTED: "approval_pending",
};

export const isSessionLifecycleState = (value: unknown): value is SessionLifecycleState => (
  typeof value === "string" && SESSION_LIFECYCLE_STATES.has(value as SessionLifecycleState)
);

export const isSessionParkedReason = (value: unknown): value is SessionParkedReason => (
  typeof value === "string" && SESSION_PARKED_REASONS.has(value as SessionParkedReason)
);

export const isSessionLifecycleEventType = (value: unknown): value is SessionLifecycleEventType => (
  typeof value === "string" && SESSION_LIFECYCLE_EVENT_TYPES.has(value as SessionLifecycleEventType)
);

export const canOwnerResumeParkedSession = (
  parkedReason: SessionParkedReason | null | undefined,
): boolean => {
  const normalized = parkedReason ?? "manual";
  return OWNER_RESUMABLE_PARKED_REASON_SET.has(normalized);
};

export const canTakeoverParkedSession = (
  parkedReason: SessionParkedReason | null | undefined,
): boolean => {
  const normalized = parkedReason ?? "manual";
  return TAKEOVER_ALLOWED_PARKED_REASON_SET.has(normalized);
};

export const canAutoResumeSession = (
  lifecycleState: SessionLifecycleState | null | undefined,
  parkedReason: SessionParkedReason | null | undefined,
): boolean => {
  const normalizedState = lifecycleState ?? "live";
  if (normalizedState === "closed") return false;
  if (normalizedState !== "parked") return true;
  const normalized = parkedReason ?? "manual";
  return AUTO_RESUME_ALLOWED_PARKED_REASON_SET.has(normalized);
};

export const getSessionLifecycleNextState = (
  currentState: SessionLifecycleState,
  eventType: SessionLifecycleEventType,
): SessionLifecycleState | null => (
  SESSION_LIFECYCLE_TRANSITIONS[currentState][eventType] ?? null
);

export const applySessionLifecycleTransition = (
  currentState: SessionLifecycleState,
  eventType: SessionLifecycleEventType,
  options?: {
    currentParkedReason?: SessionParkedReason;
    parkedReason?: SessionParkedReason;
  },
): SessionLifecycleTransitionResult | null => {
  const toState = getSessionLifecycleNextState(currentState, eventType);
  if (!toState) return null;

  if (toState === "parked") {
    const parkedReason =
      options?.parkedReason
      ?? DEFAULT_PARKED_REASON_BY_EVENT[eventType]
      ?? options?.currentParkedReason
      ?? "manual";
    return {
      fromState: currentState,
      toState,
      eventType,
      parkedReason,
    };
  }

  return {
    fromState: currentState,
    toState,
    eventType,
  };
};

export const isSessionLifecycleEventRecord = (value: unknown): value is SessionLifecycleEventRecord => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.sessionId === "string"
    && isSessionLifecycleEventType(obj.eventType)
    && isSessionLifecycleState(obj.fromState)
    && isSessionLifecycleState(obj.toState)
    && (obj.reason === undefined || typeof obj.reason === "string")
    && (obj.parkedReason === undefined || isSessionParkedReason(obj.parkedReason))
    && (
      obj.actorPrincipalType === undefined
      || obj.actorPrincipalType === "user"
      || obj.actorPrincipalType === "service_account"
    )
    && (obj.actorPrincipalId === undefined || typeof obj.actorPrincipalId === "string")
    && (obj.metadata === undefined || typeof obj.metadata === "string")
    && typeof obj.createdAt === "string"
  );
};
