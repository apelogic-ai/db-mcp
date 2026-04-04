/**
 * Feed component — scrolling message log rendered as Markdown.
 */
import { Markdown, type Component, type MarkdownTheme } from "@mariozechner/pi-tui";
import chalk from "chalk";

export interface FeedMessage {
  id: string;
  role: "system" | "user" | "assistant" | "tool" | "error";
  text: string;
}

export class Feed implements Component {
  private messages: FeedMessage[] = [];
  private seenIds = new Set<string>();
  private markdown: Markdown;
  private theme: MarkdownTheme;
  private dirty = true;

  constructor(theme: MarkdownTheme) {
    this.theme = theme;
    this.markdown = new Markdown("", 1, 0, theme);
  }

  addMessage(msg: FeedMessage): void {
    if (this.seenIds.has(msg.id)) return;
    this.seenIds.add(msg.id);
    this.messages.push(msg);
    this.dirty = true;
    this.rebuildMarkdown();
  }

  /** Append a delta to the last assistant message (for streaming). */
  appendDelta(text: string): void {
    const last = this.messages[this.messages.length - 1];
    if (last?.role === "assistant") {
      last.text += text;
      this.dirty = true;
      this.rebuildMarkdown();
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
          parts.push(msg.text || "_thinking..._");
          break;
        case "tool":
          parts.push(`\`${msg.text}\``);
          break;
        case "error":
          parts.push(`**Error:** ${msg.text}`);
          break;
      }
    }
    this.markdown.setText(parts.join("\n\n"));
  }
}
