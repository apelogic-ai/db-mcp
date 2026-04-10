import { describe, it, expect } from "vitest";
import {
  type TraceEntry,
  type DisclosureLevel,
  applyDisclosure,
  anonymizeEntry,
} from "../src/types";

const makeEntry = (overrides?: Partial<TraceEntry>): TraceEntry => ({
  // SAFE
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

  // MODERATE
  toolName: "Bash",
  toolCallId: "tool_123",
  filePath: "/src/query.ts",
  command: "uv run pytest tests/",
  taskSummary: null,
  gitRepo: "github.com:acme/db-mcp",
  gitBranch: "main",
  gitCommit: "abc123",

  // SENSITIVE
  userPrompt: null,
  assistantText: null,
  thinking: null,
  reasoning: null,
  systemPrompt: null,

  // HIGH RISK
  toolResultContent: null,
  fileContent: null,
  stdout: null,
  queryData: null,

  ...overrides,
});

describe("applyDisclosure", () => {
  it("basic: keeps only SAFE fields", () => {
    const entry = makeEntry({
      command: "cat /etc/passwd",
      userPrompt: "show me salaries",
      toolResultContent: '[{"salary": 150000}]',
    });

    const result = applyDisclosure(entry, "basic");

    // SAFE fields present
    expect(result.id).toBe("test-001");
    expect(result.timestamp).toBe("2026-04-10T12:00:00Z");
    expect(result.agent).toBe("claude_code");
    expect(result.tokenUsage).toBeDefined();
    expect(result.model).toBe("claude-opus-4-6");
    expect(result.entryType).toBe("tool_call");
    expect(result.toolName).toBe("Bash");

    // MODERATE stripped
    expect(result.command).toBeNull();
    expect(result.filePath).toBeNull();

    // SENSITIVE stripped
    expect(result.userPrompt).toBeNull();

    // HIGH RISK stripped
    expect(result.toolResultContent).toBeNull();
  });

  it("moderate: keeps SAFE + MODERATE", () => {
    const entry = makeEntry({
      command: "uv run pytest",
      userPrompt: "fix the bug",
      toolResultContent: "3 passed",
    });

    const result = applyDisclosure(entry, "moderate");

    expect(result.command).toBe("uv run pytest");
    expect(result.filePath).toBe("/src/query.ts");
    expect(result.gitRepo).toBe("github.com:acme/db-mcp");

    // SENSITIVE stripped
    expect(result.userPrompt).toBeNull();

    // HIGH RISK stripped
    expect(result.toolResultContent).toBeNull();
  });

  it("sensitive: keeps SAFE + MODERATE + SENSITIVE", () => {
    const entry = makeEntry({
      userPrompt: "how many active users?",
      assistantText: "There are 1,247 active users.",
      thinking: "I need to check the users table...",
      toolResultContent: '[{"count": 1247}]',
    });

    const result = applyDisclosure(entry, "sensitive");

    expect(result.userPrompt).toBe("how many active users?");
    expect(result.assistantText).toBe("There are 1,247 active users.");
    expect(result.thinking).toBe("I need to check the users table...");

    // HIGH RISK still stripped
    expect(result.toolResultContent).toBeNull();
  });

  it("HIGH RISK is NEVER included regardless of level", () => {
    const entry = makeEntry({
      toolResultContent: '[{"salary": 150000, "name": "Alice"}]',
      fileContent: "SECRET_KEY=abc123",
      stdout: "password: hunter2",
      queryData: '[{"ssn": "123-45-6789"}]',
    });

    for (const level of ["basic", "moderate", "sensitive"] as DisclosureLevel[]) {
      const result = applyDisclosure(entry, level);
      expect(result.toolResultContent).toBeNull();
      expect(result.fileContent).toBeNull();
      expect(result.stdout).toBeNull();
      expect(result.queryData).toBeNull();
    }
  });

  it("basic still includes toolName for analytics", () => {
    const result = applyDisclosure(makeEntry(), "basic");
    expect(result.toolName).toBe("Bash");
    expect(result.entryType).toBe("tool_call");
  });
});

describe("anonymizeEntry", () => {
  it("replaces developer with deterministic hash", () => {
    const entry = makeEntry();
    const anon = anonymizeEntry(entry);

    expect(anon.developer).toMatch(/^anon:[a-f0-9]{12}$/);
    expect(anon.developer).not.toContain("alice");
  });

  it("replaces machine with deterministic hash", () => {
    const entry = makeEntry();
    const anon = anonymizeEntry(entry);

    expect(anon.machine).toMatch(/^anon:[a-f0-9]{12}$/);
    expect(anon.machine).not.toContain("alice-mac");
  });

  it("same developer always produces same hash", () => {
    const e1 = anonymizeEntry(makeEntry({ developer: "bob@acme.com" }));
    const e2 = anonymizeEntry(makeEntry({ developer: "bob@acme.com" }));
    expect(e1.developer).toBe(e2.developer);
  });

  it("different developers produce different hashes", () => {
    const e1 = anonymizeEntry(makeEntry({ developer: "alice@acme.com" }));
    const e2 = anonymizeEntry(makeEntry({ developer: "bob@acme.com" }));
    expect(e1.developer).not.toBe(e2.developer);
  });

  it("preserves all other fields", () => {
    const entry = makeEntry({ userPrompt: "test prompt" });
    const anon = anonymizeEntry(entry);

    expect(anon.id).toBe(entry.id);
    expect(anon.timestamp).toBe(entry.timestamp);
    expect(anon.userPrompt).toBe("test prompt");
    expect(anon.toolName).toBe("Bash");
  });
});
