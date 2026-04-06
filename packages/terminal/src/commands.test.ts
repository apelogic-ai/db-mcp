import { describe, it, expect } from "vitest";
import { SLASH_COMMANDS } from "./commands.js";

describe("SLASH_COMMANDS", () => {
  it("is a non-empty array", () => {
    expect(SLASH_COMMANDS.length).toBeGreaterThan(0);
  });

  it("every command has name and description", () => {
    for (const cmd of SLASH_COMMANDS) {
      expect(cmd.name).toBeTruthy();
      expect(cmd.description).toBeTruthy();
    }
  });

  it("has no duplicate names", () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("includes essential commands", () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(names).toContain("help");
    expect(names).toContain("clear");
    expect(names).toContain("quit");
    expect(names).toContain("connections");
    expect(names).toContain("use");
    expect(names).toContain("status");
  });

  it("includes onboarding commands", () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(names).toContain("doctor");
    expect(names).toContain("playground");
    expect(names).toContain("init");
  });

  it("includes vault management commands", () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(names).toContain("examples");
    expect(names).toContain("sync");
    expect(names).toContain("session");
  });
});
