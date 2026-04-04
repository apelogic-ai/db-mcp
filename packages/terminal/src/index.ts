#!/usr/bin/env node
/**
 * db-mcp TUI — terminal interface for database queries via ACP agent.
 */

// Suppress console.log from acp-bridge debug output — TUI uses the feed, not console
const _origLog = console.log;
console.log = () => {};  // eslint-disable-line
import {
  TUI,
  ProcessTerminal,
  Editor,
  CombinedAutocompleteProvider,
} from "@mariozechner/pi-tui";
import { Agent, type AgentEvent } from "./acp/index.js";
import { Feed } from "./feed.js";
import { StatusBar } from "./status-bar.js";
import { SLASH_COMMANDS } from "./commands.js";
import { editorTheme, markdownTheme } from "./theme.js";

const BASE_URL = process.env.DB_MCP_URL ?? "http://localhost:8080";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Bundled ACP adapters — checked in order. */
const BUNDLED_AGENTS = [
  "claude-agent-acp",  // @agentclientprotocol/claude-agent-acp (npm)
  "codex-acp",         // codex-acp (cargo install codex-acp)
];

function resolveAgentCommand(): string[] {
  if (process.env.DB_MCP_AGENT) {
    return process.env.DB_MCP_AGENT.split(" ");
  }
  // Look for bundled binary in node_modules/.bin/
  const binDir = resolve(__dirname, "..", "node_modules", ".bin");
  for (const name of BUNDLED_AGENTS) {
    const localBin = resolve(binDir, name);
    if (existsSync(localBin)) {
      return [localBin];
    }
  }
  // Fall back to PATH lookup
  return ["claude-agent-acp"];
}

const AGENT_CMD = resolveAgentCommand();

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

const terminal = new ProcessTerminal();
const tui = new TUI(terminal, true);

const feed = new Feed(markdownTheme);
const editor = new Editor(tui, editorTheme, { paddingX: 1 });
const statusBar = new StatusBar();

const agent = new Agent({
  command: AGENT_CMD,
  mcpUrl: `${BASE_URL}/mcp`,
});

// Wire slash commands into the editor's autocomplete
const slashProvider = new CombinedAutocompleteProvider(SLASH_COMMANDS);
editor.setAutocompleteProvider(slashProvider);

// Catch Ctrl+C in raw mode (stdin sends \x03, not SIGINT)
tui.addInputListener((data: string) => {
  if (data === "\x03") {
    shutdown();
    return { consume: true };
  }
  return undefined;
});

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
    `Agent: \`${AGENT_CMD[0]?.split("/").pop()}\` · Server: \`${BASE_URL}\``,
    "",
    "_Press Ctrl+C to exit._",
  ].join("\n"),
});

// ---------------------------------------------------------------------------
// Agent event handler
// ---------------------------------------------------------------------------

let currentAssistantId: string | null = null;

function handleAgentEvent(event: AgentEvent): void {
  switch (event.type) {
    case "text_delta":
      if (currentAssistantId) {
        feed.appendDelta(event.delta);
      }
      break;
    case "thinking_delta":
      // Could render thinking separately, for now skip
      break;
    case "tool_start":
      feed.addMessage({
        id: `tool-${Date.now()}-${Math.random()}`,
        role: "tool",
        text: `⚙ ${event.tool}`,
      });
      break;
    case "tool_end":
      // Tool completed — agent will summarize the result
      break;
    case "error":
      feed.addMessage({
        id: `agent-err-${Date.now()}`,
        role: "error",
        text: event.message,
      });
      break;
    case "done":
      currentAssistantId = null;
      break;
  }
  tui.requestRender();
}

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
        text: [
          `Server: ${statusBar["state"].healthy ? "✓ healthy" : "✗ disconnected"}`,
          `Connection: ${statusBar["state"].connection || "none"}`,
          `Agent: ${agent.connected ? "✓ connected" : "○ not connected"} (${agent.commandName})`,
          agent.sessionId ? `Session: ${agent.sessionId}` : "",
        ].filter(Boolean).join(" · "),
      });
      break;

    case "/agent":
      if (agent.connected) {
        feed.addMessage({
          id: `agent-${Date.now()}`,
          role: "system",
          text: `Agent connected: \`${agent.commandName}\` · Session: ${agent.sessionId}`,
        });
      } else {
        feed.addMessage({
          id: `agent-${Date.now()}`,
          role: "system",
          text: [
            `Agent: \`${agent.commandName}\` — not connected.`,
            "",
            "Type any question to auto-connect, or set agent with:",
            "`DB_MCP_AGENT=claude-agent-acp db-mcp tui`",
          ].join("\n"),
        });
      }
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

  // Auto-connect agent on first prompt
  if (!agent.connected) {
    feed.addMessage({
      id: `connecting-${Date.now()}`,
      role: "system",
      text: `_Connecting to agent \`${agent.commandName}\`..._`,
    });
    tui.requestRender();

    try {
      await agent.connect(handleAgentEvent);
      statusBar.update({ agent: agent.commandName, agentConnected: true });
      feed.addMessage({
        id: `connected-${Date.now()}`,
        role: "system",
        text: `Agent connected. Session: ${agent.sessionId}`,
      });
      tui.requestRender();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      feed.addMessage({
        id: `agent-fail-${Date.now()}`,
        role: "error",
        text: [
          `Failed to connect to agent: ${msg}`,
          "",
          "Make sure the ACP adapter is installed:",
          "```",
          "npm i -g @agentclientprotocol/claude-agent-acp",
          "```",
          "Then set: `DB_MCP_AGENT=claude-agent-acp`",
        ].join("\n"),
      });
      tui.requestRender();
      return;
    }
  }

  // Start streaming response
  currentAssistantId = `assistant-${Date.now()}`;
  feed.startAssistant(currentAssistantId);
  tui.requestRender();

  try {
    await agent.prompt(text);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    feed.addMessage({
      id: `prompt-err-${Date.now()}`,
      role: "error",
      text: `Agent error: ${msg}`,
    });
  }

  currentAssistantId = null;
  tui.requestRender();
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

async function shutdown(): Promise<void> {
  clearInterval(pollInterval);
  await agent.disconnect();
  tui.stop();
  terminal.showCursor();
  // Disable Kitty keyboard protocol and reset terminal state
  process.stdout.write("\x1b[?1u");   // pop Kitty keyboard flags
  process.stdout.write("\x1b[?25h");  // show cursor
  await terminal.drainInput(1000, 100);
  process.exit(0);
}

process.on("SIGINT", () => shutdown());
process.on("SIGTERM", () => shutdown());

// Initial status check, then start
refreshStatus().then(() => {
  tui.start();
  tui.requestRender();
});
