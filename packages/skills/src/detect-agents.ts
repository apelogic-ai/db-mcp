/**
 * Detect which coding agents are installed on the system.
 * Checks known directories for each agent and reports what's found.
 */

import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

export interface DetectedAgent {
  id: string;
  name: string;
  installed: boolean;
  skillsDir: string | null;
  format: "skill_md" | "cursor_rules" | "agents_md";
  existingDbMcpSkills: string[];
}

interface AgentDef {
  id: string;
  name: string;
  /** Directories to check (relative to home). First existing one wins. */
  checkDirs: string[];
  /** Where skills are installed (relative to home) */
  skillsPath: string;
  format: "skill_md" | "cursor_rules" | "agents_md";
}

const AGENT_DEFS: AgentDef[] = [
  {
    id: "claude_code",
    name: "Claude Code",
    checkDirs: [".claude/skills", ".claude"],
    skillsPath: ".claude/skills",
    format: "skill_md",
  },
  {
    id: "codex",
    name: "Codex (OpenAI)",
    checkDirs: [".codex"],
    skillsPath: ".codex/skills",
    format: "skill_md",
  },
  {
    id: "cursor",
    name: "Cursor",
    checkDirs: [
      "Library/Application Support/Cursor",  // macOS
      ".config/Cursor",                        // Linux
    ],
    skillsPath: ".cursor/rules",
    format: "cursor_rules",
  },
];

/**
 * Detect installed agents and their skill state.
 */
export function detectAgents(homeDir: string): DetectedAgent[] {
  return AGENT_DEFS.map((def) => {
    const installed = def.checkDirs.some((d) =>
      existsSync(join(homeDir, d)),
    );

    const skillsDir = installed ? join(homeDir, def.skillsPath) : null;

    // Check for existing db-mcp skills
    const existingDbMcpSkills: string[] = [];
    if (skillsDir && existsSync(skillsDir)) {
      try {
        for (const entry of readdirSync(skillsDir)) {
          if (entry.startsWith("db-mcp-")) {
            existingDbMcpSkills.push(entry);
          }
        }
      } catch { /* can't read dir */ }
    }

    return {
      id: def.id,
      name: def.name,
      installed,
      skillsDir,
      format: def.format,
      existingDbMcpSkills,
    };
  });
}
