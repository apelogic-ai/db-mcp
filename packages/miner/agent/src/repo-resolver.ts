/**
 * Repo resolver — maps agent trace sources to git repositories.
 *
 * Claude Code: project directory name is a mangled local path
 * Codex: session_meta entry contains cwd
 * Cursor: workspace hash → resolve from VS Code state (not yet implemented)
 */

import { existsSync } from "node:fs";
import { execSync } from "node:child_process";

export interface RepoInfo {
  localPath: string;
  remote: string | null;
  repoName: string | null;
  orgName: string | null;
}

/**
 * Resolve a local path to its git remote info.
 * Returns null if the path doesn't exist or isn't a git repo.
 */
export function resolveRepoFromPath(localPath: string): RepoInfo | null {
  if (!existsSync(localPath)) return null;

  let remote: string | null = null;
  try {
    remote = execSync("git remote get-url origin", {
      cwd: localPath,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch {
    // Not a git repo or no remote
  }

  if (!remote) {
    // Check if it's a git repo at all
    try {
      execSync("git rev-parse --git-dir", {
        cwd: localPath,
        encoding: "utf-8",
        stdio: ["pipe", "pipe", "pipe"],
      });
      // Git repo but no remote
      return { localPath, remote: null, repoName: null, orgName: null };
    } catch {
      return null; // Not a git repo
    }
  }

  // Parse org/repo from remote URL
  // Handles: git@github.com:acme/my-project.git
  //          https://github.com/acme/my-project.git
  const { orgName, repoName } = parseRemoteUrl(remote);

  return { localPath, remote, repoName, orgName };
}

function parseRemoteUrl(url: string): { orgName: string | null; repoName: string | null } {
  // SSH: git@github.com:acme/my-project.git
  const sshMatch = url.match(/[:/]([^/]+)\/([^/]+?)(?:\.git)?$/);
  if (sshMatch) {
    return { orgName: sshMatch[1], repoName: sshMatch[2] };
  }
  // HTTPS: https://github.com/acme/my-project.git
  const httpsMatch = url.match(/\/([^/]+)\/([^/]+?)(?:\.git)?$/);
  if (httpsMatch) {
    return { orgName: httpsMatch[1], repoName: httpsMatch[2] };
  }
  return { orgName: null, repoName: null };
}

/**
 * Demangle a Claude Code project directory name back to a local path.
 *
 * Claude Code replaces slashes with dashes:
 *   -Users-lbelyaev-dev-db-mcp → /Users/lbelyaev/dev/db-mcp
 *
 * The challenge: dashes in directory names (e.g., "db-mcp") are
 * indistinguishable from path separators. We resolve ambiguity by
 * testing which paths actually exist on disk.
 */
export function resolveRepoFromClaudeProject(projectName: string): string | null {
  if (!projectName || !projectName.startsWith("-")) return null;

  // Split on dashes, then try combinations to find existing paths
  const segments = projectName.slice(1).split("-"); // remove leading dash
  return findExistingPath(segments, 0, "/");
}

/**
 * Recursively try combining segments with "/" or "-" to find a path
 * that exists on disk. Greedy: tries longer names first.
 */
function findExistingPath(
  segments: string[],
  index: number,
  prefix: string,
): string | null {
  if (index >= segments.length) {
    return existsSync(prefix) ? prefix : null;
  }

  // Try joining progressively more segments with dashes (longest match first)
  for (let end = segments.length; end > index; end--) {
    const name = segments.slice(index, end).join("-");
    const candidate = prefix + (prefix.endsWith("/") ? "" : "/") + name;

    if (existsSync(candidate)) {
      if (end === segments.length) return candidate;
      const rest = findExistingPath(segments, end, candidate);
      if (rest) return rest;
    }
  }

  return null;
}

/**
 * Extract the working directory from a Codex session's JSONL lines.
 * Looks for the session_meta entry which contains the cwd field.
 */
export function extractCwdFromCodexSession(lines: string[]): string | null {
  for (const line of lines) {
    try {
      const entry = JSON.parse(line) as Record<string, unknown>;
      if (entry.type !== "session_meta") continue;

      const payload = entry.payload as Record<string, unknown> | undefined;
      if (!payload) continue;

      const cwd = payload.cwd;
      if (typeof cwd === "string" && cwd) return cwd;
    } catch {
      continue;
    }
  }
  return null;
}
