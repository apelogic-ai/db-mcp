/**
 * Feed component — scrolling message log rendered as Markdown.
 */
import { Markdown, type Component, type MarkdownTheme } from "@mariozechner/pi-tui";

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
    this.currentTurn = { tools: [], text: "", completed: false };
    // Add a placeholder message that the turn renderer will replace
    this.messages.push({ id, role: "assistant", text: "" });
    this.dirty = true;
    this.rebuildMarkdown();
  }

  /** Mark the current turn as completed — compacts tool calls. */
  completeTurn(): void {
    if (this.currentTurn) {
      // Bake the turn's text into the assistant message
      let assistantMsg: FeedMessage | undefined;
      for (let i = this.messages.length - 1; i >= 0; i--) {
        if (this.messages[i]!.role === "assistant") { assistantMsg = this.messages[i]; break; }
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
    return `├ \`${tool}\``;
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
              // Compacted: show summary
              parts.push(`├ _${tools.length} tool calls: ${tools.slice(0, 3).join(", ")}..._`);
            } else {
              // Show each tool on its own line (single block, no empty lines)
              const toolBlock = tools.map(t => this.formatToolLine(t)).join("\n");
              parts.push(toolBlock);
            }
          }

          // Render response text
          if (text) {
            parts.push(text);
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
