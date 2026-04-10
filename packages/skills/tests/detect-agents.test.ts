import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { detectAgents, type DetectedAgent } from "../src/detect-agents";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "skills-detect-"));
}

describe("detectAgents", () => {
  it("detects Claude Code when ~/.claude/skills/ exists", () => {
    const home = makeTmpDir();
    mkdirSync(join(home, ".claude", "skills"), { recursive: true });

    const agents = detectAgents(home);
    const claude = agents.find((a) => a.id === "claude_code");
    expect(claude).toBeDefined();
    expect(claude!.installed).toBe(true);
    expect(claude!.skillsDir).toContain(".claude/skills");
  });

  it("detects Codex when ~/.codex/ exists", () => {
    const home = makeTmpDir();
    mkdirSync(join(home, ".codex"), { recursive: true });

    const agents = detectAgents(home);
    const codex = agents.find((a) => a.id === "codex");
    expect(codex).toBeDefined();
    expect(codex!.installed).toBe(true);
  });

  it("detects Cursor when app support dir exists", () => {
    const home = makeTmpDir();
    // macOS path
    mkdirSync(join(home, "Library", "Application Support", "Cursor"), {
      recursive: true,
    });

    const agents = detectAgents(home);
    const cursor = agents.find((a) => a.id === "cursor");
    expect(cursor).toBeDefined();
    expect(cursor!.installed).toBe(true);
  });

  it("marks agents as not installed when dirs don't exist", () => {
    const home = makeTmpDir();
    // No agent dirs

    const agents = detectAgents(home);
    for (const a of agents) {
      expect(a.installed).toBe(false);
    }
  });

  it("returns all known agents regardless of installation status", () => {
    const home = makeTmpDir();
    const agents = detectAgents(home);
    const ids = agents.map((a) => a.id);
    expect(ids).toContain("claude_code");
    expect(ids).toContain("codex");
    expect(ids).toContain("cursor");
  });

  it("checks for existing db-mcp skills", () => {
    const home = makeTmpDir();
    const skillsDir = join(home, ".claude", "skills", "db-mcp-query");
    mkdirSync(skillsDir, { recursive: true });
    writeFileSync(join(skillsDir, "SKILL.md"), "# Query skill");

    const agents = detectAgents(home);
    const claude = agents.find((a) => a.id === "claude_code")!;
    expect(claude.existingDbMcpSkills).toContain("db-mcp-query");
  });
});
