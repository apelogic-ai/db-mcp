import { describe, it, expect, beforeEach, vi } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, appendFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Daemon, type DaemonConfig } from "../src/daemon";
import type { ShippedBatch } from "../src/shipper";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-daemon-"));
}

function setupFakeClaudeTrace(dir: string, lines: string[]): string {
  const projectDir = join(dir, "projects", "test-proj");
  mkdirSync(projectDir, { recursive: true });
  const file = join(projectDir, "session.jsonl");
  writeFileSync(file, lines.join("\n") + "\n");
  return file;
}

describe("Daemon", () => {
  let stateDir: string;
  let claudeDir: string;
  let shipped: ShippedBatch[];

  beforeEach(() => {
    stateDir = makeTmpDir();
    claudeDir = makeTmpDir();
    shipped = [];
  });

  function makeConfig(overrides?: Partial<DaemonConfig>): DaemonConfig {
    return {
      claudeDir,
      codexDir: "/nonexistent",
      cursorDir: "/nonexistent",
      stateDir,
      pollIntervalMs: 100,
      redactSecrets: true,
      developer: "test@example.com",
      onShip: async (batch) => { shipped.push(batch); },
      ...overrides,
    };
  }

  it("processes traces on pollOnce()", () => {
    setupFakeClaudeTrace(claudeDir, [
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "hi" }] } }),
    ]);

    const daemon = new Daemon(makeConfig());
    daemon.pollOnce();

    expect(shipped).toHaveLength(1);
    expect(shipped[0].agent).toBe("claude_code");
    expect(shipped[0].developer).toBe("test@example.com");
  });

  it("deduplicates across polls", () => {
    setupFakeClaudeTrace(claudeDir, [
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "hi" }] } }),
    ]);

    const daemon = new Daemon(makeConfig());
    daemon.pollOnce();
    const firstCount = shipped.length;

    daemon.pollOnce();
    expect(shipped.length).toBe(firstCount); // no new data
  });

  it("picks up new entries on subsequent polls", () => {
    const file = setupFakeClaudeTrace(claudeDir, [
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "first" }] } }),
    ]);

    const daemon = new Daemon(makeConfig());
    daemon.pollOnce();
    const firstEntries = shipped.reduce((s, b) => s + b.entries.length, 0);

    // Append new entry
    appendFileSync(file,
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:01:00Z", message: { content: [{ type: "text", text: "second" }] } }) + "\n",
    );

    daemon.pollOnce();
    const totalEntries = shipped.reduce((s, b) => s + b.entries.length, 0);
    expect(totalEntries).toBeGreaterThan(firstEntries);
  });

  it("redacts secrets by default", () => {
    setupFakeClaudeTrace(claudeDir, [
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "key: AKIAIOSFODNN7EXAMPLE" }] } }),
    ]);

    const daemon = new Daemon(makeConfig());
    daemon.pollOnce();

    const allContent = shipped.flatMap((b) => b.entries).join("");
    expect(allContent).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(allContent).toContain("[REDACTED:");
  });

  it("emits progress events", () => {
    setupFakeClaudeTrace(claudeDir, [
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "hi" }] } }),
    ]);

    const progress: string[] = [];
    const daemon = new Daemon(makeConfig({
      onProgress: (msg) => progress.push(msg),
    }));
    daemon.pollOnce();

    expect(progress.length).toBeGreaterThan(0);
    expect(progress.some((p) => p.includes("source"))).toBe(true);
  });
});
