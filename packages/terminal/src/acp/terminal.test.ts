import { describe, it, expect } from "vitest";
import {
  handleCreateTerminal,
  handleTerminalOutput,
  handleWaitForTerminalExit,
  handleReleaseTerminal,
} from "./terminal.js";

describe("Terminal handler", () => {
  describe("handleCreateTerminal", () => {
    it("returns a terminal id", () => {
      const result = handleCreateTerminal({ command: "echo", args: ["hello"] });
      expect(result.terminalId).toMatch(/^term-\d+$/);
      // Cleanup
      handleReleaseTerminal({ terminalId: result.terminalId });
    });

    it("returns unique ids", () => {
      const a = handleCreateTerminal({ command: "echo", args: ["a"] });
      const b = handleCreateTerminal({ command: "echo", args: ["b"] });
      expect(a.terminalId).not.toBe(b.terminalId);
      handleReleaseTerminal({ terminalId: a.terminalId });
      handleReleaseTerminal({ terminalId: b.terminalId });
    });
  });

  describe("handleTerminalOutput", () => {
    it("returns output of a simple command", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "echo",
        args: ["hello world"],
      });
      const result = await handleTerminalOutput({ terminalId });
      expect(result.output).toContain("hello world");
      expect(result.exitStatus?.exitCode).toBe(0);
      handleReleaseTerminal({ terminalId });
    });

    it("captures stderr", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "sh",
        args: ["-c", "echo err >&2"],
      });
      const result = await handleTerminalOutput({ terminalId });
      expect(result.output).toContain("err");
      handleReleaseTerminal({ terminalId });
    });

    it("returns exit code for failing command", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "sh",
        args: ["-c", "exit 42"],
      });
      const result = await handleTerminalOutput({ terminalId });
      expect(result.exitStatus?.exitCode).not.toBe(0);
      handleReleaseTerminal({ terminalId });
    });

    it("returns error for unknown terminal", async () => {
      const result = await handleTerminalOutput({ terminalId: "term-nonexistent" });
      expect(result.output).toContain("not found");
      expect(result.exitStatus?.exitCode).toBe(1);
    });
  });

  describe("handleWaitForTerminalExit", () => {
    it("waits for command completion and returns exit code", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "echo",
        args: ["done"],
      });
      const result = await handleWaitForTerminalExit({ terminalId });
      expect(result.exitCode).toBe(0);
      handleReleaseTerminal({ terminalId });
    });

    it("returns exit code 1 for unknown terminal", async () => {
      const result = await handleWaitForTerminalExit({ terminalId: "term-ghost" });
      expect(result.exitCode).toBe(1);
    });
  });

  describe("handleReleaseTerminal", () => {
    it("releases a terminal", () => {
      const { terminalId } = handleCreateTerminal({
        command: "echo",
        args: ["release-me"],
      });
      const result = handleReleaseTerminal({ terminalId });
      expect(result).toEqual({});
    });

    it("output returns not found after release", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "echo",
        args: ["gone"],
      });
      await handleTerminalOutput({ terminalId });
      handleReleaseTerminal({ terminalId });
      const result = await handleTerminalOutput({ terminalId });
      expect(result.output).toContain("not found");
    });
  });

  describe("environment and cwd", () => {
    it("passes custom environment variables", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "sh",
        args: ["-c", "echo $TEST_VAR"],
        env: [{ name: "TEST_VAR", value: "custom_value" }],
      });
      const result = await handleTerminalOutput({ terminalId });
      expect(result.output).toContain("custom_value");
      handleReleaseTerminal({ terminalId });
    });

    it("uses specified cwd", async () => {
      const { terminalId } = handleCreateTerminal({
        command: "pwd",
        cwd: "/tmp",
      });
      const result = await handleTerminalOutput({ terminalId });
      expect(result.output.trim()).toMatch(/\/tmp|\/private\/tmp/);
      handleReleaseTerminal({ terminalId });
    });
  });
});
