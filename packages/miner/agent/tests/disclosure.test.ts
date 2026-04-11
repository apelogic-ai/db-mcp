import { describe, it, expect } from "vitest";
import {
  type TraceEntry,
  type DisclosureLevel,
  type FieldPolicy,
  applyDisclosure,
  applyFieldPolicy,
  DEFAULT_FIELD_POLICIES,
} from "../src/types";

const makeEntry = (): TraceEntry => ({
  id: "test-001",
  timestamp: "2026-04-10T12:00:00Z",
  agent: "claude_code",
  sessionId: "sess-abc",
  entryType: "tool_call",
  role: "assistant",
  model: "claude-opus-4-6",
  tokenUsage: { input: 100, output: 50, cacheRead: 500, reasoning: 0 },
  developer: "alice@acme.com",
  machine: "alice-mac",
  project: "db-mcp",
  toolName: "Bash",
  toolCallId: "tool_123",
  filePath: "/src/query.ts",
  command: "uv run pytest tests/",
  taskSummary: "Fixed the bug",
  gitRepo: "github.com:acme/db-mcp",
  gitBranch: "main",
  gitCommit: "abc123",
  userPrompt: "fix the tests",
  assistantText: "I'll run pytest",
  thinking: "need to check test files",
  reasoning: "analyzing the error",
  systemPrompt: "You are a helpful assistant",
  toolResultContent: '{"salary": 150000}',
  fileContent: "SECRET_KEY=abc123",
  stdout: "password: hunter2",
  queryData: '[{"ssn": "123-45-6789"}]',
});

describe("applyFieldPolicy", () => {
  it("keeps fields that are true, nulls fields that are false", () => {
    const policy: FieldPolicy = {
      ...DEFAULT_FIELD_POLICIES.basic,
      command: true,    // override: include command in basic
    };

    const entry = makeEntry();
    const result = applyFieldPolicy(entry, policy);

    // Explicitly included
    expect(result.command).toBe("uv run pytest tests/");
    expect(result.toolName).toBe("Bash");
    expect(result.model).toBe("claude-opus-4-6");

    // Excluded by basic policy
    expect(result.userPrompt).toBeNull();
    expect(result.toolResultContent).toBeNull();
  });

  it("DEFAULT_FIELD_POLICIES.basic matches applyDisclosure basic", () => {
    const entry = makeEntry();
    const fromLevel = applyDisclosure(entry, "basic");
    const fromPolicy = applyFieldPolicy(entry, DEFAULT_FIELD_POLICIES.basic);

    // All nullable fields should match
    for (const key of Object.keys(entry) as (keyof TraceEntry)[]) {
      if (key === "id" || key === "timestamp" || key === "agent" ||
          key === "sessionId" || key === "entryType" || key === "role" ||
          key === "developer" || key === "machine" || key === "project") continue;
      expect(fromPolicy[key]).toEqual(fromLevel[key]);
    }
  });

  it("DEFAULT_FIELD_POLICIES.moderate matches applyDisclosure moderate", () => {
    const entry = makeEntry();
    const fromLevel = applyDisclosure(entry, "moderate");
    const fromPolicy = applyFieldPolicy(entry, DEFAULT_FIELD_POLICIES.moderate);

    for (const key of Object.keys(entry) as (keyof TraceEntry)[]) {
      if (["id","timestamp","agent","sessionId","entryType","role","developer","machine","project"].includes(key)) continue;
      expect(fromPolicy[key]).toEqual(fromLevel[key]);
    }
  });

  it("DEFAULT_FIELD_POLICIES.sensitive matches applyDisclosure sensitive", () => {
    const entry = makeEntry();
    const fromLevel = applyDisclosure(entry, "sensitive");
    const fromPolicy = applyFieldPolicy(entry, DEFAULT_FIELD_POLICIES.sensitive);

    for (const key of Object.keys(entry) as (keyof TraceEntry)[]) {
      if (["id","timestamp","agent","sessionId","entryType","role","developer","machine","project"].includes(key)) continue;
      expect(fromPolicy[key]).toEqual(fromLevel[key]);
    }
  });

  it("allows per-field overrides on top of a tier", () => {
    const policy: FieldPolicy = {
      ...DEFAULT_FIELD_POLICIES.basic,
      userPrompt: true,     // include prompt in basic
      toolName: false,       // exclude tool name from basic
    };

    const entry = makeEntry();
    const result = applyFieldPolicy(entry, policy);

    expect(result.userPrompt).toBe("fix the tests");
    expect(result.toolName).toBeNull();
  });

  it("HIGH_RISK fields are always null regardless of policy", () => {
    const policy: FieldPolicy = {
      ...DEFAULT_FIELD_POLICIES.sensitive,
      toolResultContent: true,  // try to force include
      fileContent: true,
      stdout: true,
      queryData: true,
    };

    const entry = makeEntry();
    const result = applyFieldPolicy(entry, policy);

    // HIGH_RISK is hardcoded to always strip
    expect(result.toolResultContent).toBeNull();
    expect(result.fileContent).toBeNull();
    expect(result.stdout).toBeNull();
    expect(result.queryData).toBeNull();
  });
});
