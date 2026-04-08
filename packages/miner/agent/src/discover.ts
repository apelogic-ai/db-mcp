/**
 * Discover agent trace sources on the local machine.
 * Scans known directories for Claude Code, Codex, and other agents.
 */

import { existsSync, readdirSync, statSync } from "node:fs";
import { join, basename } from "node:path";

export type AgentType = "claude_code" | "codex" | "cursor";

export interface TraceSource {
  agent: AgentType;
  project: string;
  files: string[];
}

export interface DiscoverOptions {
  claudeCodeDir?: string;
  codexDir?: string;
  cursorDir?: string;
}

/**
 * Discover all trace file sources from configured agent directories.
 */
export function discoverTraceSources(options: DiscoverOptions): TraceSource[] {
  const sources: TraceSource[] = [];

  if (options.claudeCodeDir) {
    sources.push(...discoverClaudeCode(options.claudeCodeDir));
  }
  if (options.codexDir) {
    sources.push(...discoverCodex(options.codexDir));
  }
  if (options.cursorDir) {
    sources.push(...discoverCursor(options.cursorDir));
  }

  return sources;
}

function discoverClaudeCode(claudeDir: string): TraceSource[] {
  const projectsDir = join(claudeDir, "projects");
  if (!existsSync(projectsDir)) return [];

  const sources: TraceSource[] = [];

  for (const entry of readdirSync(projectsDir)) {
    const projectPath = join(projectsDir, entry);
    if (!statSync(projectPath).isDirectory()) continue;

    const jsonlFiles = readdirSync(projectPath).filter((f) =>
      f.endsWith(".jsonl")
    );
    if (jsonlFiles.length === 0) continue;

    sources.push({
      agent: "claude_code",
      project: entry,
      files: jsonlFiles.map((f) => join(projectPath, f)),
    });
  }

  return sources;
}

function discoverCodex(codexDir: string): TraceSource[] {
  const sessionsDir = join(codexDir, "sessions");
  if (!existsSync(sessionsDir)) return [];

  const files = collectJsonlRecursive(sessionsDir);
  if (files.length === 0) return [];

  // Group as a single source (Codex organizes by date, not project)
  return [
    {
      agent: "codex",
      project: "all",
      files,
    },
  ];
}

function discoverCursor(cursorDir: string): TraceSource[] {
  const sources: TraceSource[] = [];

  // Global state.vscdb
  const globalDb = join(cursorDir, "User", "globalStorage", "state.vscdb");
  if (existsSync(globalDb)) {
    sources.push({
      agent: "cursor",
      project: "global",
      files: [globalDb],
    });
  }

  // Per-workspace state.vscdb files
  const wsDir = join(cursorDir, "User", "workspaceStorage");
  if (existsSync(wsDir)) {
    for (const entry of readdirSync(wsDir)) {
      const wsDb = join(wsDir, entry, "state.vscdb");
      if (existsSync(wsDb)) {
        sources.push({
          agent: "cursor",
          project: `workspace:${entry}`,
          files: [wsDb],
        });
      }
    }
  }

  return sources;
}

function collectJsonlRecursive(dir: string): string[] {
  const results: string[] = [];

  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      results.push(...collectJsonlRecursive(full));
    } else if (entry.endsWith(".jsonl")) {
      results.push(full);
    }
  }

  return results;
}
