export type SessionInterruptionKind = "approval_pending";

export interface SessionInterruption {
  kind: SessionInterruptionKind;
  createdAt: string;
  requestId?: string;
  tool?: string;
  description?: string;
  task?: string;
  executionId?: string;
  parentExecutionId?: string;
  turnId?: string;
  stale?: boolean;
}

const SESSION_INTERRUPTION_KINDS = new Set<SessionInterruptionKind>([
  "approval_pending",
]);

export const isSessionInterruptionKind = (value: unknown): value is SessionInterruptionKind => (
  typeof value === "string" && SESSION_INTERRUPTION_KINDS.has(value as SessionInterruptionKind)
);

export const isSessionInterruption = (value: unknown): value is SessionInterruption => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    isSessionInterruptionKind(obj.kind)
    && typeof obj.createdAt === "string"
    && (obj.requestId === undefined || typeof obj.requestId === "string")
    && (obj.tool === undefined || typeof obj.tool === "string")
    && (obj.description === undefined || typeof obj.description === "string")
    && (obj.task === undefined || typeof obj.task === "string")
    && (obj.executionId === undefined || typeof obj.executionId === "string")
    && (obj.parentExecutionId === undefined || typeof obj.parentExecutionId === "string")
    && (obj.turnId === undefined || typeof obj.turnId === "string")
    && (obj.stale === undefined || typeof obj.stale === "boolean")
  );
};
