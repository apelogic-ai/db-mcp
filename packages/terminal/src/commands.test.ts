import { describe, it, expect } from "vitest";
import { buildSlashCommands } from "./commands.js";

const COMMANDS = buildSlashCommands("http://localhost:9999");

describe("buildSlashCommands", () => {
  it("returns a non-empty array", () => {
    expect(COMMANDS.length).toBeGreaterThan(0);
  });

  it("every command has name and description", () => {
    for (const cmd of COMMANDS) {
      expect(cmd.name).toBeTruthy();
      expect(cmd.description).toBeTruthy();
    }
  });

  it("has no duplicate names", () => {
    const names = COMMANDS.map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("includes essential commands", () => {
    const names = COMMANDS.map((c) => c.name);
    expect(names).toContain("help");
    expect(names).toContain("clear");
    expect(names).toContain("quit");
    expect(names).toContain("connections");
    expect(names).toContain("use");
    expect(names).toContain("status");
  });

  it("includes onboarding commands", () => {
    const names = COMMANDS.map((c) => c.name);
    expect(names).toContain("doctor");
    expect(names).toContain("playground");
    expect(names).toContain("init");
  });

  it("/use has getArgumentCompletions", () => {
    const useCmd = COMMANDS.find((c) => c.name === "use");
    expect(useCmd?.getArgumentCompletions).toBeTypeOf("function");
  });

  it("/env has getArgumentCompletions", () => {
    const envCmd = COMMANDS.find((c) => c.name === "env");
    expect(envCmd?.getArgumentCompletions).toBeTypeOf("function");
  });

  it("/schema has subcommand completions", async () => {
    const schemaCmd = COMMANDS.find((c) => c.name === "schema");
    const results = await schemaCmd?.getArgumentCompletions?.("");
    expect(results).not.toBeNull();
    expect(results!.length).toBeGreaterThan(0);
    expect(results!.map((r) => r.value)).toContain("show");
    expect(results!.map((r) => r.value)).toContain("tables");
  });

  it("/schema filters by prefix", async () => {
    const schemaCmd = COMMANDS.find((c) => c.name === "schema");
    const results = await schemaCmd?.getArgumentCompletions?.("sh");
    expect(results).toHaveLength(1);
    expect(results![0]!.value).toBe("show");
  });

  it("/rules has subcommand completions", async () => {
    const rulesCmd = COMMANDS.find((c) => c.name === "rules");
    const results = await rulesCmd?.getArgumentCompletions?.("");
    expect(results!.map((r) => r.value)).toContain("list");
    expect(results!.map((r) => r.value)).toContain("add");
  });

  it("/env suggests key names after connection", async () => {
    const envCmd = COMMANDS.find((c) => c.name === "env");
    const results = await envCmd?.getArgumentCompletions?.("nova ");
    expect(results).not.toBeNull();
    expect(results!.map((r) => r.value)).toContain("DATABASE_URL");
    expect(results!.map((r) => r.value)).toContain("API_KEY");
  });
});
