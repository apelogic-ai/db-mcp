import { describe, it, expect, beforeEach } from "vitest";
import { StatusBar } from "./status-bar.js";

describe("StatusBar", () => {
  let bar: StatusBar;

  beforeEach(() => {
    bar = new StatusBar();
  });

  describe("initial state", () => {
    it("starts with defaults", () => {
      expect(bar.state.connection).toBe("none");
      expect(bar.state.healthy).toBe(false);
      expect(bar.state.agent).toBe("");
      expect(bar.state.agentConnected).toBe(false);
      expect(bar.state.contextUsed).toBe(0);
      expect(bar.state.cost).toBe(0);
    });
  });

  describe("update", () => {
    it("partial update merges into state", () => {
      bar.update({ connection: "nova", healthy: true });
      expect(bar.state.connection).toBe("nova");
      expect(bar.state.healthy).toBe(true);
      expect(bar.state.agent).toBe(""); // unchanged
    });

    it("updates agent info", () => {
      bar.update({ agent: "claude-agent-acp", agentConnected: true });
      expect(bar.state.agent).toBe("claude-agent-acp");
      expect(bar.state.agentConnected).toBe(true);
    });
  });

  describe("updateUsage", () => {
    it("sets context and accumulates cost", () => {
      bar.updateUsage({ used: 10000, size: 1000000, cost: 0.05, currency: "USD" });
      expect(bar.state.contextUsed).toBe(10000);
      expect(bar.state.contextSize).toBe(1000000);
      expect(bar.state.cost).toBe(0.05);
      expect(bar.state.currency).toBe("USD");
    });

    it("accumulates cost across multiple updates", () => {
      bar.updateUsage({ used: 5000, size: 1000000, cost: 0.03, currency: "USD" });
      bar.updateUsage({ used: 15000, size: 1000000, cost: 0.07, currency: "USD" });
      expect(bar.state.cost).toBeCloseTo(0.10);
      expect(bar.state.contextUsed).toBe(15000); // overwritten, not accumulated
    });
  });

  describe("render", () => {
    it("renders connection name", () => {
      bar.update({ connection: "nova", healthy: true });
      const lines = bar.render(80);
      expect(lines).toHaveLength(1);
      expect(lines[0]).toContain("nova");
    });

    it("renders agent when set", () => {
      bar.update({ agent: "claude-agent-acp", agentConnected: true });
      const lines = bar.render(80);
      expect(lines[0]).toContain("claude-agent-acp");
    });

    it("renders context usage when non-zero", () => {
      bar.update({ healthy: true });
      bar.updateUsage({ used: 25000, size: 1000000, cost: 0.15, currency: "USD" });
      const lines = bar.render(120);
      expect(lines[0]).toContain("25.0k");
      expect(lines[0]).toContain("1.0M");
      expect(lines[0]).toContain("$0.15");
    });

    it("pads to full width", () => {
      bar.update({ connection: "test", healthy: true });
      const lines = bar.render(80);
      // Strip ANSI codes and check length
      const visible = lines[0].replace(/\x1b\[[0-9;]*m/g, "");
      expect(visible.length).toBe(80);
    });

    it("does not render cost when zero", () => {
      bar.update({ connection: "test", healthy: true });
      const lines = bar.render(80);
      expect(lines[0]).not.toContain("$");
    });
  });
});
