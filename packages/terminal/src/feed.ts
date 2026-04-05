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

/** Strip mcp__db-mcp__ prefix from tool names. */
function shortToolName(name: string): string {
  return name.replace(/^mcp__db-mcp__/, "").replace(/^mcp__.*?__/, "");
}

/**
 * A turn groups: user prompt → tool calls → assistant response.
 * Tool calls are tracked separately for compaction after the turn completes.
 */
interface Turn {
  tools: string[];       // formatted tool descriptions
  text: string;          // accumulated assistant text
  completed: boolean;    // true after prompt() resolves
}

export class Feed implements Component {
  private messages: FeedMessage[] = [];
  private seenIds = new Set<string>();
  private markdown: Markdown;
  private dirty = true;
  private currentTurn: Turn | null = null;

  constructor(theme: MarkdownTheme) {
    this.markdown = new Markdown("", 1, 0, theme);
  }

  addMessage(msg: FeedMessage): void {
    if (this.seenIds.has(msg.id)) return;
    this.seenIds.add(msg.id);

    if (msg.role === "tool") {
      // Accumulate tool calls into the current turn
      if (this.currentTurn) {
        // If there's text before this tool call, add a line break
        // so text doesn't cram into the next chunk
        if (this.currentTurn.text && !this.currentTurn.text.endsWith("\n")) {
          this.currentTurn.text += "\n\n";
        }
        this.currentTurn.tools.push(shortToolName(msg.text));
      }
      // Don't add to messages — tools are rendered from the turn
    } else {
      this.messages.push(msg);
    }

    this.dirty = true;
    this.rebuildMarkdown();
  }

  appendDelta(text: string): void {
    if (this.currentTurn) {
      this.currentTurn.text += text;
      this.dirty = true;
      this.rebuildMarkdown();
    }
  }

  startAssistant(id: string): void {
    // Complete any previous turn first
    if (this.currentTurn) {
      this.completeTurn();
    }
    this.currentTurn = { tools: [], text: "", completed: false };
    this.messages.push({ id, role: "assistant", text: "" });
    this.dirty = true;
    this.rebuildMarkdown();
  }

  /** Mark the current turn as completed — compacts tool calls. */
  completeTurn(): void {
    if (this.currentTurn) {
      // Find the assistant message for THIS turn (the last non-completed one)
      let assistantMsg: FeedMessage | undefined;
      for (let i = this.messages.length - 1; i >= 0; i--) {
        const m = this.messages[i]!;
        if (m.role === "assistant" && !(m as any)._completed) {
          assistantMsg = m;
          break;
        }
      }
      if (assistantMsg) {
        assistantMsg.text = this.currentTurn.text;
        (assistantMsg as any)._tools = [...this.currentTurn.tools];
        (assistantMsg as any)._completed = true;
      }
      this.currentTurn = null;
      this.dirty = true;
      this.rebuildMarkdown();
    }
  }

  clear(): void {
    this.messages = [];
    this.seenIds.clear();
    this.currentTurn = null;
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

  private formatToolLine(tool: string): string {
    // Use chalk for dimmed yellow — markdown italic/code don't render well
    return chalk.dim.yellow(`├ ${tool}`);
  }

  private formatToolSummary(tools: string[]): string {
    const preview = tools.slice(0, 3).join(", ");
    const suffix = tools.length > 3 ? "…" : "";
    return chalk.dim.yellow(`├ ${tools.length} tools: ${preview}${suffix}`);
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
        case "assistant": {
          const completed = (msg as any)._completed;
          const tools: string[] = completed
            ? (msg as any)._tools ?? []
            : this.currentTurn?.tools ?? [];
          const text = completed
            ? msg.text
            : this.currentTurn?.text ?? "";

          // Render tool calls
          if (tools.length > 0) {
            if (completed && tools.length > 3) {
              parts.push(this.formatToolSummary(tools));
            } else {
              // Each tool on its own line, no empty lines between
              parts.push(tools.map(t => this.formatToolLine(t)).join("\n"));
            }
          }

          // Render response text
          if (text) {
            // Agent streams without line breaks — insert paragraph breaks at
            // natural sentence boundaries (.:A or :A patterns)
            let normalized = text;
            // Convert existing single \n to \n\n for markdown paragraph breaks
            normalized = normalized.replace(/(?<!\n)\n(?!\n)/g, "\n\n");
            // Insert breaks where sentences end with : or . followed by capital letter
            normalized = normalized.replace(/([.:])([A-Z])/g, "$1\n\n$2");
            parts.push(normalized);
          } else if (!completed) {
            parts.push("_thinking..._");
          }
          break;
        }
        case "error":
          parts.push(`**Error:** ${msg.text}`);
          break;
      }
    }

    this.markdown.setText(parts.join("\n\n"));
  }
}
