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
    if (msg.role === "tool") {
      msg = { ...msg, text: shortToolName(msg.text) };
    }
    this.messages.push(msg);
    this.dirty = true;
    this.rebuildMarkdown();
  }

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
    // Group messages into turns: user → tools → assistant response
    // Tool calls should appear between the question and the answer
    const parts: string[] = [];
    let i = 0;

    while (i < this.messages.length) {
      const msg = this.messages[i]!;

      if (msg.role === "assistant") {
        // Collect all tool messages that follow this assistant message
        const tools: string[] = [];
        let j = i + 1;
        while (j < this.messages.length && this.messages[j]!.role === "tool") {
          tools.push(this.messages[j]!.text);
          j++;
        }

        // Render tools FIRST (above the response)
        if (tools.length > 0) {
          const toolLine = tools.map(t => `\`${t}\``).join(" → ");
          parts.push(`  ├ ${toolLine}`);
        }

        // Then render assistant text
        if (msg.text) {
          parts.push(msg.text);
        } else {
          parts.push("_thinking..._");
        }

        i = j;  // skip past the tool messages we consumed
        continue;
      }

      switch (msg.role) {
        case "system":
          parts.push(msg.text);
          break;
        case "user":
          parts.push(`**> ${msg.text}**`);
          break;
        case "tool":
          // Stray tool message (not after an assistant) — render inline
          parts.push(`  ├ \`${msg.text}\``);
          break;
        case "error":
          parts.push(`**Error:** ${msg.text}`);
          break;
      }
      i++;
    }

    this.markdown.setText(parts.join("\n\n"));
  }
}
