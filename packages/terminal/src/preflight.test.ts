import { describe, it, expect } from "vitest";
import { which } from "./preflight.js";

describe("which", () => {
  it("finds a common binary", () => {
    const result = which("sh");
    expect(result).not.toBeNull();
    expect(result).toContain("sh");
  });

  it("returns null for nonexistent binary", () => {
    expect(which("definitely-not-a-real-binary-xyz")).toBeNull();
  });

  it("finds node", () => {
    const result = which("node");
    expect(result).not.toBeNull();
  });
});
