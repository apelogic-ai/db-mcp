/**
 * Install a db-mcp skill to a specific agent in its native format.
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync, cpSync } from "node:fs";
import { join } from "node:path";

export interface InstallTarget {
  agentId: string;
  skillsDir: string;
  format: "skill_md" | "cursor_rules" | "agents_md";
}

export interface InstallResult {
  success: boolean;
  path?: string;
  error?: string;
}

/**
 * Strip YAML frontmatter from a SKILL.md file.
 * Returns the content after the closing --- delimiter.
 */
function stripFrontmatter(content: string): string {
  if (!content.startsWith("---")) return content;
  const endIdx = content.indexOf("---", 3);
  if (endIdx === -1) return content;
  return content.slice(endIdx + 3).trimStart();
}

/**
 * Install a skill from the skills source directory to the target agent.
 *
 * @param skillName - Skill name (e.g., "query", "connections")
 * @param skillsSrcDir - Root of the skills package (contains query/, connections/ dirs)
 * @param target - Where and how to install
 */
export function installSkill(
  skillName: string,
  skillsSrcDir: string,
  target: InstallTarget,
): InstallResult {
  const srcDir = join(skillsSrcDir, skillName);

  if (!existsSync(srcDir)) {
    return { success: false, error: `Skill "${skillName}" not found at ${srcDir}` };
  }

  const srcSkillMd = join(srcDir, "SKILL.md");
  if (!existsSync(srcSkillMd)) {
    return { success: false, error: `Skill "${skillName}" has no SKILL.md` };
  }

  const content = readFileSync(srcSkillMd, "utf-8");

  mkdirSync(target.skillsDir, { recursive: true });

  switch (target.format) {
    case "skill_md": {
      // Claude Code / Codex: copy SKILL.md into a named directory
      const destDir = join(target.skillsDir, `db-mcp-${skillName}`);
      mkdirSync(destDir, { recursive: true });
      writeFileSync(join(destDir, "SKILL.md"), content);
      return { success: true, path: join(destDir, "SKILL.md") };
    }

    case "cursor_rules": {
      // Cursor: strip frontmatter, write as flat .md file in rules/
      const stripped = stripFrontmatter(content);
      const destPath = join(target.skillsDir, `db-mcp-${skillName}.md`);
      writeFileSync(destPath, stripped);
      return { success: true, path: destPath };
    }

    case "agents_md": {
      // AGENTS.md: append skill content as a section
      const stripped = stripFrontmatter(content);
      const agentsMdPath = join(target.skillsDir, "AGENTS.md");
      const existing = existsSync(agentsMdPath)
        ? readFileSync(agentsMdPath, "utf-8")
        : "";
      const section = `\n\n## db-mcp: ${skillName}\n\n${stripped}`;
      writeFileSync(agentsMdPath, existing + section);
      return { success: true, path: agentsMdPath };
    }

    default:
      return { success: false, error: `Unknown format: ${target.format}` };
  }
}
