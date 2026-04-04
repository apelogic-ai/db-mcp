/**
 * Feed component — scrolling message log rendered as Markdown.
 */
import { Markdown, type Component, type MarkdownTheme } from "@mariozechner/pi-tui";

export interface FeedMessage {
  id: string;
  role: "system" | "user" | "assistant" | "tool" | "error";
  text: string;
}

/** Strip mcp__db-mcp__ prefix from tool names for display. */
function shortToolName(name: string): string {
  return name
    .replace(/^mcp__db-mcp__/, "")
    .replace(/^mcp__.*?__/, "");
}

export class Feed implements Component {
  private messages: FeedMessage[] = [];
  private seenIds = new Set<string>();
  private markdown: Markdown;
  private dirty = true;

  constructor(theme: MarkdownTheme) {
    this.markdown = new Markdown("", 1, 0, theme);
  }

  addMessage(msg: FeedMessage): void {
    if (this.seenIds.has(msg.id)) return;
    this.seenIds.add(msg.id);
    // Tool messages use shortened names
    if (msg.role === "tool") {
      msg = { ...msg, text: shortToolName(msg.text) };
    }
    this.messages.push(msg);
    this.dirty = true;
    this.rebuildMarkdown();
  }

  /** Append a delta to the latest assistant message (for streaming). */
  appendDelta(text: string): void {
    for (let i = this.messages.length - 1; i >= 0; i--) {
      if (this.messages[i]!.role === "assistant") {
        this.messages[i]!.text += text;
        this.dirty = true;
        this.rebuildMarkdown();
        return;
      }
    }
  }

  /** Start a new streaming assistant message. */
  startAssistant(id: string): void {
    this.addMessage({ id, role: "assistant", text: "" });
  }

  clear(): void {
    this.messages = [];
    this.seenIds.clear();
    this.dirty = true;
    this.rebuildMarkdown();
  }

  get messageCount(): number {
    return this.messages.length;
  }

  invalidate(): void {
    this.dirty = true;
  }

  render(width: number): string[] {
    return this.markdown.render(width);
  }

  private rebuildMarkdown(): void {
    const parts: string[] = [];
    for (const msg of this.messages) {
      switch (msg.role) {
        case "system":
          parts.push(msg.text);
          break;
        case "user":
          parts.push(`**> ${msg.text}**`);
          break;
        case "assistant":
          // Render assistant text — preserve line breaks from streaming
          if (msg.text) {
            parts.push(msg.text);
          } else {
            parts.push("_thinking..._");
          }
          break;
        case "tool":
          // Compact tool indicator — indented, dimmed
          parts.push(`    ⎿ _${msg.text}_`);
          break;
        case "error":
          parts.push(`**Error:** ${msg.text}`);
          break;
      }
    }
    this.markdown.setText(parts.join("\n\n"));
  }
}
