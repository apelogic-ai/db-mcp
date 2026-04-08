import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { discoverTraceSources, type TraceSource } from "../src/discover";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-discover-"));
}

describe("discoverTraceSources", () => {
  it("discovers Claude Code trace directories", () => {
    const root = makeTmpDir();
    const claudeDir = join(root, ".claude", "projects", "-Users-test-dev-myproject");
    mkdirSync(claudeDir, { recursive: true });
    writeFileSync(join(claudeDir, "abc123.jsonl"), '{"type":"user"}\n');

    const sources = discoverTraceSources({
      claudeCodeDir: join(root, ".claude"),
    });

    expect(sources).toHaveLength(1);
    expect(sources[0].agent).toBe("claude_code");
    expect(sources[0].files).toHaveLength(1);
    expect(sources[0].project).toBe("-Users-test-dev-myproject");
  });

  it("discovers Codex trace directories", () => {
    const root = makeTmpDir();
    const codexDir = join(root, ".codex", "sessions", "2026", "04", "08");
    mkdirSync(codexDir, { recursive: true });
    writeFileSync(join(codexDir, "rollout-2026-04-08.jsonl"), '{"type":"session_meta"}\n');

    const sources = discoverTraceSources({
      codexDir: join(root, ".codex"),
    });

    expect(sources).toHaveLength(1);
    expect(sources[0].agent).toBe("codex");
    expect(sources[0].files.length).toBeGreaterThanOrEqual(1);
  });

  it("returns empty when directories don't exist", () => {
    const sources = discoverTraceSources({
      claudeCodeDir: "/nonexistent/.claude",
      codexDir: "/nonexistent/.codex",
    });
    expect(sources).toEqual([]);
  });

  it("discovers multiple projects from Claude Code", () => {
    const root = makeTmpDir();
    const projectsDir = join(root, ".claude", "projects");
    mkdirSync(join(projectsDir, "project-a"), { recursive: true });
    mkdirSync(join(projectsDir, "project-b"), { recursive: true });
    writeFileSync(join(projectsDir, "project-a", "s1.jsonl"), '{"type":"user"}\n');
    writeFileSync(join(projectsDir, "project-b", "s2.jsonl"), '{"type":"user"}\n');

    const sources = discoverTraceSources({
      claudeCodeDir: join(root, ".claude"),
    });

    const projects = sources.map((s) => s.project).sort();
    expect(projects).toEqual(["project-a", "project-b"]);
  });

  it("ignores non-jsonl files", () => {
    const root = makeTmpDir();
    const projectDir = join(root, ".claude", "projects", "test-proj");
    mkdirSync(projectDir, { recursive: true });
    writeFileSync(join(projectDir, "session.jsonl"), '{"type":"user"}\n');
    writeFileSync(join(projectDir, "memory"), "not a trace");
    writeFileSync(join(projectDir, "sessions-index.json"), "{}");

    const sources = discoverTraceSources({
      claudeCodeDir: join(root, ".claude"),
    });

    expect(sources).toHaveLength(1);
    expect(sources[0].files).toHaveLength(1);
    expect(sources[0].files[0]).toContain("session.jsonl");
  });
});
