import { describe, it, expect, beforeEach } from "vitest";
import { Feed, type FeedMessage } from "./feed.js";
import { markdownTheme } from "./theme.js";

function createFeed(): Feed {
  return new Feed(markdownTheme);
}

describe("Feed", () => {
  let feed: Feed;

  beforeEach(() => {
    feed = createFeed();
  });

  // -----------------------------------------------------------------------
  // addMessage
  // -----------------------------------------------------------------------

  describe("addMessage", () => {
    it("adds a system message", () => {
      feed.addMessage({ id: "sys-1", role: "system", text: "Hello" });
      expect(feed.messageCount).toBe(1);
    });

    it("adds a user message", () => {
      feed.addMessage({ id: "user-1", role: "user", text: "question" });
      expect(feed.messageCount).toBe(1);
    });

    it("adds an error message", () => {
      feed.addMessage({ id: "err-1", role: "error", text: "boom" });
      expect(feed.messageCount).toBe(1);
    });

    it("deduplicates by id", () => {
      feed.addMessage({ id: "dup", role: "system", text: "first" });
      feed.addMessage({ id: "dup", role: "system", text: "second" });
      expect(feed.messageCount).toBe(1);
    });

    it("tool messages go to current turn, not messages", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "tool-1", role: "tool", text: "shell: ls" });
      // tool messages are NOT added to messages array
      // they go to currentTurn.tools
      expect(feed.messageCount).toBe(1); // only the assistant message
    });

    it("tool messages without a turn are ignored", () => {
      feed.addMessage({ id: "tool-1", role: "tool", text: "shell: ls" });
      expect(feed.messageCount).toBe(0);
    });
  });

  // -----------------------------------------------------------------------
  // shortToolName (via addMessage)
  // -----------------------------------------------------------------------

  describe("tool name stripping", () => {
    it("strips mcp__db-mcp__ prefix", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "mcp__db-mcp__shell" });
      // Access private field to verify
      const turn = (feed as any).currentTurn;
      expect(turn.tools).toEqual(["shell"]);
    });

    it("strips other mcp__ prefixes", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "mcp__other__run" });
      const turn = (feed as any).currentTurn;
      expect(turn.tools).toEqual(["run"]);
    });

    it("keeps non-mcp tool names unchanged", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "Terminal" });
      const turn = (feed as any).currentTurn;
      expect(turn.tools).toEqual(["Terminal"]);
    });
  });

  // -----------------------------------------------------------------------
  // appendDelta
  // -----------------------------------------------------------------------

  describe("appendDelta", () => {
    it("appends text to current turn", () => {
      feed.startAssistant("a-1");
      feed.appendDelta("Hello ");
      feed.appendDelta("world");
      const turn = (feed as any).currentTurn;
      expect(turn.text).toBe("Hello world");
    });

    it("does nothing without a current turn", () => {
      // Should not throw
      feed.appendDelta("orphan text");
    });
  });

  // -----------------------------------------------------------------------
  // updateLastTool
  // -----------------------------------------------------------------------

  describe("updateLastTool", () => {
    it("updates the last tool entry", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "Terminal" });
      feed.updateLastTool("db-mcp rules list");
      const turn = (feed as any).currentTurn;
      expect(turn.tools).toEqual(["db-mcp rules list"]);
    });

    it("only updates the last tool", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "Terminal" });
      feed.addMessage({ id: "t-2", role: "tool", text: "Terminal" });
      feed.updateLastTool("db-mcp schema show");
      const turn = (feed as any).currentTurn;
      expect(turn.tools).toEqual(["Terminal", "db-mcp schema show"]);
    });

    it("does nothing without tools", () => {
      feed.startAssistant("a-1");
      feed.updateLastTool("orphan detail");
      const turn = (feed as any).currentTurn;
      expect(turn.tools).toEqual([]);
    });

    it("does nothing without a current turn", () => {
      // Should not throw
      feed.updateLastTool("no turn");
    });
  });

  // -----------------------------------------------------------------------
  // startAssistant / completeTurn
  // -----------------------------------------------------------------------

  describe("turn lifecycle", () => {
    it("startAssistant creates a turn and adds assistant message", () => {
      feed.startAssistant("a-1");
      expect(feed.messageCount).toBe(1);
      expect((feed as any).currentTurn).not.toBeNull();
    });

    it("completeTurn finalizes the turn", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "shell" });
      feed.appendDelta("Result: 42");
      feed.completeTurn();

      expect((feed as any).currentTurn).toBeNull();
      // The assistant message should have the text and tools baked in
      const msg = (feed as any).messages.find(
        (m: FeedMessage) => m.role === "assistant"
      );
      expect(msg.text).toBe("Result: 42");
      expect((msg as any)._tools).toEqual(["shell"]);
      expect((msg as any)._completed).toBe(true);
    });

    it("starting a new turn completes the previous one", () => {
      feed.startAssistant("a-1");
      feed.appendDelta("first");
      feed.startAssistant("a-2");
      // First turn should be completed
      const msgs = (feed as any).messages;
      const first = msgs.find((m: any) => m.id === "a-1");
      expect((first as any)._completed).toBe(true);
      expect(first.text).toBe("first");
    });
  });

  // -----------------------------------------------------------------------
  // clear
  // -----------------------------------------------------------------------

  describe("clear", () => {
    it("removes all messages and resets turn", () => {
      feed.addMessage({ id: "s-1", role: "system", text: "hi" });
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "shell" });
      feed.clear();

      expect(feed.messageCount).toBe(0);
      expect((feed as any).currentTurn).toBeNull();
    });

    it("allows new messages after clear with same ids", () => {
      feed.addMessage({ id: "s-1", role: "system", text: "first" });
      feed.clear();
      feed.addMessage({ id: "s-1", role: "system", text: "second" });
      expect(feed.messageCount).toBe(1);
    });
  });

  // -----------------------------------------------------------------------
  // render
  // -----------------------------------------------------------------------

  describe("render", () => {
    it("renders without crashing", () => {
      feed.addMessage({ id: "s-1", role: "system", text: "welcome" });
      const lines = feed.render(80);
      expect(lines.length).toBeGreaterThan(0);
    });

    it("includes prefix lines", () => {
      feed.setPrefixLines(["LOGO LINE 1", "LOGO LINE 2"]);
      const lines = feed.render(80);
      expect(lines[0]).toBe("LOGO LINE 1");
      expect(lines[1]).toBe("LOGO LINE 2");
    });

    it("renders tool lines during active turn", () => {
      feed.startAssistant("a-1");
      feed.addMessage({ id: "t-1", role: "tool", text: "shell" });
      feed.addMessage({ id: "t-2", role: "tool", text: "validate_sql" });
      const lines = feed.render(80);
      const toolLines = lines.filter((l) => l.includes("├"));
      expect(toolLines.length).toBe(2);
    });

    it("renders tool summary for completed turns with >3 tools", () => {
      feed.startAssistant("a-1");
      for (let i = 0; i < 5; i++) {
        feed.addMessage({ id: `t-${i}`, role: "tool", text: `tool-${i}` });
      }
      feed.appendDelta("done");
      feed.completeTurn();
      const lines = feed.render(80);
      const summaryLines = lines.filter((l) => l.includes("5 tools:"));
      expect(summaryLines.length).toBe(1);
    });

    it("shows 'thinking...' when turn has no text", () => {
      feed.startAssistant("a-1");
      const lines = feed.render(80);
      const thinkingLines = lines.filter((l) => l.includes("thinking"));
      expect(thinkingLines.length).toBe(1);
    });
  });
});
