import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import Database from "better-sqlite3";
import { resolveCursorWorkspacePath } from "../src/repo-resolver";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-cursor-repo-"));
}

function createCursorGlobalDb(dir: string, workspaces: Record<string, string>): string {
  const globalDir = join(dir, "User", "globalStorage");
  mkdirSync(globalDir, { recursive: true });
  const dbPath = join(globalDir, "state.vscdb");

  const db = new Database(dbPath);
  db.exec("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)");

  // VS Code stores recently opened workspaces in this key
  const recentWorkspaces = Object.entries(workspaces).map(([hash, path]) => ({
    folderUri: `file://${path}`,
    // The hash in the workspaceStorage dir name is derived from the URI
  }));

  // Also store the workspace→path mapping in cursorDiskKV if it exists
  db.exec("CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)");

  // VS Code's workspaceStorage directories contain workspace.json
  for (const [hash, path] of Object.entries(workspaces)) {
    const wsDir = join(dir, "User", "workspaceStorage", hash);
    mkdirSync(wsDir, { recursive: true });
    writeFileSync(
      join(wsDir, "workspace.json"),
      JSON.stringify({ folder: `file://${path}` }),
    );
  }

  db.close();
  return dir;
}

describe("resolveCursorWorkspacePath", () => {
  it("resolves workspace hash to local path via workspace.json", () => {
    const cursorDir = makeTmpDir();
    createCursorGlobalDb(cursorDir, {
      abc123: "/Users/test/dev/my-project",
    });

    const result = resolveCursorWorkspacePath(cursorDir, "abc123");
    expect(result).toBe("/Users/test/dev/my-project");
  });

  it("handles multiple workspaces", () => {
    const cursorDir = makeTmpDir();
    createCursorGlobalDb(cursorDir, {
      hash1: "/Users/test/dev/project-a",
      hash2: "/Users/test/dev/project-b",
    });

    expect(resolveCursorWorkspacePath(cursorDir, "hash1")).toBe("/Users/test/dev/project-a");
    expect(resolveCursorWorkspacePath(cursorDir, "hash2")).toBe("/Users/test/dev/project-b");
  });

  it("returns null for unknown hash", () => {
    const cursorDir = makeTmpDir();
    createCursorGlobalDb(cursorDir, {
      known: "/Users/test/dev/exists",
    });

    expect(resolveCursorWorkspacePath(cursorDir, "unknown")).toBeNull();
  });

  it("returns null when workspace.json is missing", () => {
    const cursorDir = makeTmpDir();
    const wsDir = join(cursorDir, "User", "workspaceStorage", "empty-hash");
    mkdirSync(wsDir, { recursive: true });
    // No workspace.json

    expect(resolveCursorWorkspacePath(cursorDir, "empty-hash")).toBeNull();
  });

  it("handles file:// URI stripping", () => {
    const cursorDir = makeTmpDir();
    const wsDir = join(cursorDir, "User", "workspaceStorage", "uri-test");
    mkdirSync(wsDir, { recursive: true });
    writeFileSync(
      join(wsDir, "workspace.json"),
      JSON.stringify({ folder: "file:///Users/test/dev/uri-project" }),
    );

    const result = resolveCursorWorkspacePath(cursorDir, "uri-test");
    expect(result).toBe("/Users/test/dev/uri-project");
  });
});
