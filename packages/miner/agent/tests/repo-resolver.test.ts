import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { execSync } from "node:child_process";
import {
  resolveRepoFromPath,
  resolveRepoFromClaudeProject,
  extractCwdFromCodexSession,
  type RepoInfo,
} from "../src/repo-resolver";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-repo-"));
}

describe("resolveRepoFromPath", () => {
  it("returns git remote for a repo directory", () => {
    // Use the actual db-mcp repo
    const result = resolveRepoFromPath("/Users/lbelyaev/dev/db-mcp");
    if (result) {
      expect(result.remote).toContain("db-mcp");
      expect(result.localPath).toBe("/Users/lbelyaev/dev/db-mcp");
    }
    // Skip if path doesn't exist (CI)
  });

  it("returns null for non-git directory", () => {
    const dir = makeTmpDir();
    const result = resolveRepoFromPath(dir);
    expect(result).toBeNull();
  });

  it("returns null for nonexistent path", () => {
    expect(resolveRepoFromPath("/nonexistent/path")).toBeNull();
  });

  it("returns repo name from remote URL", () => {
    const dir = makeTmpDir();
    mkdirSync(join(dir, ".git"), { recursive: true });
    execSync("git init", { cwd: dir, stdio: "pipe" });
    execSync("git remote add origin git@github.com:acme/my-project.git", {
      cwd: dir,
      stdio: "pipe",
    });

    const result = resolveRepoFromPath(dir);
    expect(result).not.toBeNull();
    expect(result!.remote).toContain("acme/my-project");
    expect(result!.repoName).toBe("my-project");
    expect(result!.orgName).toBe("acme");
  });
});

describe("resolveRepoFromClaudeProject", () => {
  it("demangles project name using real directories", () => {
    // Create a temp structure that mimics a real path
    const root = makeTmpDir(); // e.g. /tmp/miner-repo-XXXX
    const projectDir = join(root, "dev", "my-project");
    mkdirSync(projectDir, { recursive: true });

    // Mangle the path the way Claude Code does: /tmp/miner-repo-XXXX/dev/my-project
    // → -tmp-miner-repo-XXXX-dev-my-project
    const mangled = "-" + root.slice(1).replace(/\//g, "-") + "-dev-my-project";
    const result = resolveRepoFromClaudeProject(mangled);
    expect(result).toBe(projectDir);
  });

  it("handles nested paths with real directories", () => {
    const root = makeTmpDir();
    const nested = join(root, "dev", "my-project", "packages", "core");
    mkdirSync(nested, { recursive: true });

    const mangled = "-" + root.slice(1).replace(/\//g, "-") + "-dev-my-project-packages-core";
    const result = resolveRepoFromClaudeProject(mangled);
    expect(result).toBe(nested);
  });

  it("returns null for unrecognizable names", () => {
    expect(resolveRepoFromClaudeProject("")).toBeNull();
    expect(resolveRepoFromClaudeProject("random-name")).toBeNull();
  });
});

describe("extractCwdFromCodexSession", () => {
  it("extracts cwd from session_meta entry", () => {
    const lines = [
      JSON.stringify({
        timestamp: "2026-04-08T12:00:00Z",
        type: "session_meta",
        payload: { id: "sess-1", cwd: "/Users/lbelyaev/dev/db-mcp" },
      }),
      JSON.stringify({
        timestamp: "2026-04-08T12:00:01Z",
        type: "response_item",
        payload: { type: "message", role: "user", content: [] },
      }),
    ];

    const cwd = extractCwdFromCodexSession(lines);
    expect(cwd).toBe("/Users/lbelyaev/dev/db-mcp");
  });

  it("returns null when no session_meta", () => {
    const lines = [
      JSON.stringify({ type: "response_item", payload: { type: "message" } }),
    ];
    expect(extractCwdFromCodexSession(lines)).toBeNull();
  });

  it("handles session_meta without cwd", () => {
    const lines = [
      JSON.stringify({ type: "session_meta", payload: { id: "x" } }),
    ];
    expect(extractCwdFromCodexSession(lines)).toBeNull();
  });
});
