import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { installSkill, type InstallTarget } from "../src/install-skill";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "skills-install-"));
}

// Path to the actual skill source files
const SKILLS_SRC = join(__dirname, "..");

describe("installSkill", () => {
  it("installs a skill to Claude Code format", () => {
    const home = makeTmpDir();
    const skillsDir = join(home, ".claude", "skills");
    mkdirSync(skillsDir, { recursive: true });

    const target: InstallTarget = {
      agentId: "claude_code",
      skillsDir,
      format: "skill_md",
    };

    const result = installSkill("query", SKILLS_SRC, target);
    expect(result.success).toBe(true);

    const installed = join(skillsDir, "db-mcp-query", "SKILL.md");
    expect(existsSync(installed)).toBe(true);
    const content = readFileSync(installed, "utf-8");
    expect(content).toContain("name: query");
    expect(content).toContain("Data Query Skill");
  });

  it("installs to Codex format (same as Claude Code)", () => {
    const home = makeTmpDir();
    const skillsDir = join(home, ".codex", "skills");
    mkdirSync(skillsDir, { recursive: true });

    const target: InstallTarget = {
      agentId: "codex",
      skillsDir,
      format: "skill_md",
    };

    const result = installSkill("query", SKILLS_SRC, target);
    expect(result.success).toBe(true);
    expect(existsSync(join(skillsDir, "db-mcp-query", "SKILL.md"))).toBe(true);
  });

  it("installs to Cursor format (strips frontmatter, writes to rules/)", () => {
    const home = makeTmpDir();
    const rulesDir = join(home, ".cursor", "rules");
    mkdirSync(rulesDir, { recursive: true });

    const target: InstallTarget = {
      agentId: "cursor",
      skillsDir: rulesDir,
      format: "cursor_rules",
    };

    const result = installSkill("query", SKILLS_SRC, target);
    expect(result.success).toBe(true);

    const installed = join(rulesDir, "db-mcp-query.md");
    expect(existsSync(installed)).toBe(true);
    const content = readFileSync(installed, "utf-8");
    // Should NOT have YAML frontmatter
    expect(content).not.toContain("---");
    expect(content).toContain("Data Query Skill");
  });

  it("installs the connections skill", () => {
    const home = makeTmpDir();
    const skillsDir = join(home, ".claude", "skills");
    mkdirSync(skillsDir, { recursive: true });

    const target: InstallTarget = {
      agentId: "claude_code",
      skillsDir,
      format: "skill_md",
    };

    const result = installSkill("connections", SKILLS_SRC, target);
    expect(result.success).toBe(true);
    expect(existsSync(join(skillsDir, "db-mcp-connections", "SKILL.md"))).toBe(true);
  });

  it("returns error for unknown skill", () => {
    const home = makeTmpDir();
    const target: InstallTarget = {
      agentId: "claude_code",
      skillsDir: join(home, "skills"),
      format: "skill_md",
    };

    const result = installSkill("nonexistent", SKILLS_SRC, target);
    expect(result.success).toBe(false);
    expect(result.error).toContain("not found");
  });

  it("overwrites existing installation", () => {
    const home = makeTmpDir();
    const skillsDir = join(home, ".claude", "skills");
    mkdirSync(join(skillsDir, "db-mcp-query"), { recursive: true });

    const target: InstallTarget = {
      agentId: "claude_code",
      skillsDir,
      format: "skill_md",
    };

    // Install twice — should succeed both times
    installSkill("query", SKILLS_SRC, target);
    const result = installSkill("query", SKILLS_SRC, target);
    expect(result.success).toBe(true);
  });
});
