// Policy types

import type { PrincipalType, PromptSource } from "./protocol.js";

export type PolicyAction = "allow" | "deny" | "ask";

export interface PolicyRule {
  tool: string;
  pattern?: string;
  principalType?: PrincipalType;
  principalIdPattern?: string;
  source?: PromptSource;
  workspaceIdPattern?: string;
  action: PolicyAction;
}

export interface PolicyConfig {
  rules: PolicyRule[];
}

const POLICY_ACTIONS = new Set(["allow", "deny", "ask"]);
const PRINCIPAL_TYPES = new Set(["user", "service_account"]);
const PROMPT_SOURCES = new Set(["interactive", "schedule", "hook", "api"]);

export const isPolicyConfig = (value: unknown): value is PolicyConfig => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  if (!Array.isArray(obj.rules)) return false;
  return obj.rules.every((rule: unknown) => {
    if (typeof rule !== "object" || rule === null) return false;
    const r = rule as Record<string, unknown>;
    return (
      typeof r.tool === "string" &&
      typeof r.action === "string" &&
      POLICY_ACTIONS.has(r.action) &&
      (r.pattern === undefined || typeof r.pattern === "string") &&
      (r.principalType === undefined || (typeof r.principalType === "string" && PRINCIPAL_TYPES.has(r.principalType))) &&
      (r.principalIdPattern === undefined || typeof r.principalIdPattern === "string") &&
      (r.source === undefined || (typeof r.source === "string" && PROMPT_SOURCES.has(r.source))) &&
      (r.workspaceIdPattern === undefined || typeof r.workspaceIdPattern === "string")
    );
  });
};
