import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { execSync } from "node:child_process";

const CLI = join(__dirname, "..", "src", "cli.ts");

function run(args: string, env?: Record<string, string>): { code: number; stdout: string; stderr: string } {
  try {
    const stdout = execSync(`bun ${CLI} ${args}`, {
      encoding: "utf-8",
      env: { ...process.env, ...env },
      stdio: ["pipe", "pipe", "pipe"],
    });
    return { code: 0, stdout, stderr: "" };
  } catch (err: unknown) {
    const e = err as { status: number; stdout: string; stderr: string };
    return { code: e.status ?? 1, stdout: e.stdout ?? "", stderr: e.stderr ?? "" };
  }
}

describe("CLI", () => {
  it("shows help", () => {
    const { code, stdout } = run("--help");
    expect(code).toBe(0);
    expect(stdout).toContain("miner-agent");
    expect(stdout).toContain("scan");
    expect(stdout).toContain("status");
  });

  it("shows version", () => {
    const { code, stdout } = run("--version");
    expect(code).toBe(0);
    expect(stdout).toContain("0.1.0");
  });

  it("scan discovers and processes traces", () => {
    const stateDir = mkdtempSync(join(tmpdir(), "miner-cli-"));
    const fakeClaudeDir = mkdtempSync(join(tmpdir(), "miner-claude-"));
    const projectDir = join(fakeClaudeDir, "projects", "test-proj");
    mkdirSync(projectDir, { recursive: true });
    writeFileSync(
      join(projectDir, "session.jsonl"),
      [
        JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "hello" }] } }),
        JSON.stringify({ type: "assistant", timestamp: "2026-04-08T10:00:01Z", message: { content: [{ type: "tool_use", name: "Bash", input: { command: "ls" } }], usage: { input_tokens: 100, output_tokens: 50 } } }),
      ].join("\n") + "\n",
    );

    const { code, stdout } = run(
      `scan --claude-dir ${fakeClaudeDir} --codex-dir /nonexistent --cursor-dir /nonexistent --state-dir ${stateDir}`,
    );
    expect(code).toBe(0);
    expect(stdout).toContain("test-proj");
    expect(stdout).toContain("claude_code");
  });

  it("status shows counts", () => {
    const stateDir = mkdtempSync(join(tmpdir(), "miner-cli-"));

    const { code, stdout } = run(
      `status --claude-dir /nonexistent --codex-dir /nonexistent --cursor-dir /nonexistent --state-dir ${stateDir}`,
    );
    expect(code).toBe(0);
    expect(stdout).toContain("sources");
  });

  it("scan with --dry-run does not ship", () => {
    const stateDir = mkdtempSync(join(tmpdir(), "miner-cli-"));
    const fakeClaudeDir = mkdtempSync(join(tmpdir(), "miner-claude-"));
    const projectDir = join(fakeClaudeDir, "projects", "test-proj");
    mkdirSync(projectDir, { recursive: true });
    writeFileSync(
      join(projectDir, "session.jsonl"),
      JSON.stringify({ type: "user", timestamp: "2026-04-08T10:00:00Z", message: { content: [{ type: "text", text: "hi" }] } }) + "\n",
    );

    const { code, stdout } = run(
      `scan --claude-dir ${fakeClaudeDir} --codex-dir /nonexistent --cursor-dir /nonexistent --state-dir ${stateDir} --dry-run`,
    );
    expect(code).toBe(0);
    expect(stdout).toContain("dry run");
  });
});
