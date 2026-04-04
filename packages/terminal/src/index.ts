#!/usr/bin/env node
/**
 * db-mcp TUI — terminal interface for database queries via ACP agent.
 */
import {
  TUI,
  ProcessTerminal,
  Editor,
  CombinedAutocompleteProvider,
  type SlashCommand,
} from "@mariozechner/pi-tui";
import { Feed, type FeedMessage } from "./feed.js";
import { StatusBar } from "./status-bar.js";
import { SLASH_COMMANDS } from "./commands.js";
import { editorTheme, markdownTheme } from "./theme.js";

const BASE_URL = process.env.DB_MCP_URL ?? "http://localhost:8080";

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

const terminal = new ProcessTerminal();
const tui = new TUI(terminal, true);

const feed = new Feed(markdownTheme);
const editor = new Editor(tui, editorTheme, { paddingX: 1 });
const statusBar = new StatusBar();

// Wire slash commands into the editor's autocomplete
const slashProvider = new CombinedAutocompleteProvider(SLASH_COMMANDS);
editor.setAutocompleteProvider(slashProvider);

// Layout: feed takes all space, editor + status docked at bottom
tui.addChild(feed);
tui.addChild(editor);
tui.addChild(statusBar);
tui.setFocus(editor);

// ---------------------------------------------------------------------------
// Welcome
// ---------------------------------------------------------------------------

feed.addMessage({
  id: "welcome",
  role: "system",
  text: [
    "# db-mcp",
    "",
    "Type a question to query your database. Type `/` for commands.",
    "",
    "_Press Ctrl+C to exit._",
  ].join("\n"),
});

// ---------------------------------------------------------------------------
// Input handling
// ---------------------------------------------------------------------------

editor.onSubmit = async (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return;

  editor.setText("");
  editor.addToHistory(trimmed);

  if (trimmed.startsWith("/")) {
    await handleCommand(trimmed);
  } else {
    await handlePrompt(trimmed);
  }

  tui.requestRender();
};

async function handleCommand(raw: string): Promise<void> {
  const [cmd, ...rest] = raw.split(" ");
  const arg = rest.join(" ").trim();

  switch (cmd) {
    case "/help":
      feed.addMessage({
        id: `help-${Date.now()}`,
        role: "system",
        text: [
          "**Commands:**",
          "",
          "| Command | Description |",
          "|---------|-------------|",
          ...SLASH_COMMANDS.map(
            (c) => `| \`/${c.name}\` | ${c.description} |`
          ),
          "",
          "Or type any question in natural language.",
        ].join("\n"),
      });
      break;

    case "/clear":
      feed.clear();
      break;

    case "/status":
      await refreshStatus();
      feed.addMessage({
        id: `status-${Date.now()}`,
        role: "system",
        text: `Server: ${statusBar["state"].healthy ? "healthy" : "disconnected"} · Connection: ${statusBar["state"].connection || "none"}`,
      });
      break;

    case "/quit":
      shutdown();
      break;

    default:
      feed.addMessage({
        id: `err-${Date.now()}`,
        role: "error",
        text: `Unknown command: ${cmd}`,
      });
  }
}

async function handlePrompt(text: string): Promise<void> {
  feed.addMessage({
    id: `user-${Date.now()}`,
    role: "user",
    text,
  });

  // TODO: Route through ACP agent session
  feed.addMessage({
    id: `placeholder-${Date.now()}`,
    role: "system",
    text: "_Agent not connected. Configure with `/agent`._",
  });
}

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------

async function refreshStatus(): Promise<void> {
  try {
    const resp = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(2000) });
    const data = (await resp.json()) as Record<string, string>;
    statusBar.update({
      healthy: resp.ok,
      connection: data.connection ?? "",
    });
  } catch {
    statusBar.update({ healthy: false });
  }
}

// Poll every 3 seconds
const pollInterval = setInterval(() => {
  refreshStatus().then(() => tui.requestRender());
}, 3000);

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

function shutdown(): void {
  clearInterval(pollInterval);
  tui.stop();
  terminal.showCursor();
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// Initial status check, then start
refreshStatus().then(() => {
  tui.start();
  tui.requestRender();
});
