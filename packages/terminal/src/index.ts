#!/usr/bin/env node
/**
 * db-mcp TUI — terminal interface for database queries via ACP agent.
 */

// Redirect console.log to file — acp-bridge uses it for RPC debug
// Suppressing it entirely (= () => {}) may break timing-dependent RPC flows
import { appendFileSync } from "node:fs";
const _origLog = console.log;
if (process.env.DB_MCP_DEBUG) {
  // Keep console.log visible in debug mode
} else {
  console.log = (...args: unknown[]) => {
    try {
      appendFileSync("/tmp/db-mcp-rpc.log", args.map(String).join(" ") + "\n");
    } catch {}
  };
}

// Catch unhandled rejections — show in feed, don't crash
process.on("unhandledRejection", (err) => {
  const msg = err instanceof Error ? err.message : String(err);
  try {
    feed.addMessage({ id: `unhandled-${Date.now()}`, role: "error", text: msg });
    tui.requestRender();
  } catch {
    // Feed might not be ready yet
  }
});

// Log uncaught exceptions to file
process.on("uncaughtException", (err) => {
  require("node:fs").appendFileSync("/tmp/db-mcp-tui-crash.log",
    `${new Date().toISOString()} UNCAUGHT: ${err.stack ?? err.message}\n`);
});
import {
  TUI,
  ProcessTerminal,
  Editor,
  CombinedAutocompleteProvider,
  matchesKey,
} from "@mariozechner/pi-tui";
import chalk from "chalk";
import { Agent, type AgentEvent } from "./acp/index.js";
import { Feed } from "./feed.js";
import { StatusBar } from "./status-bar.js";
import { buildSlashCommands } from "./commands.js";
import { editorTheme, markdownTheme } from "./theme.js";
import { loadPrompt } from "./prompts.js";

const BASE_URL = process.env.DB_MCP_URL ?? "http://localhost:8080";
const FORCE_FTE = process.env.DB_MCP_FTE === "1";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Bundled ACP adapters — checked in order. */
const BUNDLED_AGENTS = [
  "claude-agent-acp",  // @agentclientprotocol/claude-agent-acp (npm)
  "codex-acp",         // @zed-industries/codex-acp (npm)
];

function resolveAgentCommand(): string[] {
  if (process.env.DB_MCP_AGENT) {
    return process.env.DB_MCP_AGENT.split(" ");
  }
  // Check multiple locations for the agent binary
  const searchDirs = [
    resolve(__dirname, "..", "node_modules", ".bin"),   // repo: packages/terminal/node_modules/.bin/
    resolve(__dirname, "node_modules", ".bin"),          // bundle: terminal/node_modules/.bin/
  ];
  for (const binDir of searchDirs) {
    for (const name of BUNDLED_AGENTS) {
      const localBin = resolve(binDir, name);
      if (existsSync(localBin)) {
        return [localBin];
      }
    }
  }
  // Fall back to PATH lookup
  return ["claude-agent-acp"];
}

const AGENT_CMD = resolveAgentCommand();

/** Detect which agent runtime we're using based on the resolved command. */
function detectRuntime(cmd: string[]): "claude" | "codex" | "unknown" {
  const joined = cmd.join(" ");
  if (joined.includes("claude-agent-acp")) return "claude";
  if (joined.includes("codex-acp")) return "codex";
  return "unknown";
}

/** Pre-flight check: verify agent adapter and underlying CLI are available. */
async function checkAgentPrerequisites(): Promise<string | null> {
  const { execFileSync } = await import("node:child_process");
  const { which } = await import("./preflight.js");

  const runtime = detectRuntime(AGENT_CMD);
  const agentBin = AGENT_CMD[0]!;

  // 1. Check ACP adapter binary
  const agentFound = agentBin.includes("/") ? existsSync(agentBin) : !!which(agentBin);
  if (!agentFound) {
    const installHint = runtime === "codex"
      ? "npm i -g @zed-industries/codex-acp"
      : "npm i -g @agentclientprotocol/claude-agent-acp";
    return [
      `**ACP adapter not found:** \`${agentBin}\``,
      "",
      "Install it with:",
      "```",
      installHint,
      "```",
    ].join("\n");
  }

  // 2. Check underlying CLI
  if (runtime === "claude") {
    if (!which("claude")) {
      return [
        "**Claude Code not found.**",
        "",
        "Install it with:",
        "```",
        "npm i -g @anthropic-ai/claude-code",
        "```",
        "Then run `claude` once to authenticate.",
      ].join("\n");
    }
    // 3. Check Claude auth
    try {
      const out = execFileSync("claude", ["auth", "status"], {
        timeout: 5000, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
      });
      const status = JSON.parse(out);
      if (!status.loggedIn) {
        return [
          "**Claude Code is not authenticated.**",
          "",
          "Run: `claude auth login`",
          "Then restart the TUI.",
        ].join("\n");
      }
    } catch {}
  } else if (runtime === "codex") {
    if (!which("codex")) {
      return [
        "**Codex CLI not found.**",
        "",
        "Install it with:",
        "```",
        "npm i -g @openai/codex",
        "```",
        "Then run `codex login` to authenticate.",
      ].join("\n");
    }
    // 3. Check Codex auth
    try {
      const out = execFileSync("codex", ["login", "status"], {
        timeout: 5000, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"],
      });
      if (out.toLowerCase().includes("not logged in") || out.toLowerCase().includes("no api key")) {
        return [
          "**Codex is not authenticated.**",
          "",
          "Run: `codex login`",
          "Then restart the TUI.",
        ].join("\n");
      }
    } catch {}
  }

  return null;
}

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
const SLASH_COMMANDS = buildSlashCommands(BASE_URL);
const slashProvider = new CombinedAutocompleteProvider(SLASH_COMMANDS);
editor.setAutocompleteProvider(slashProvider);

// Catch Ctrl+C in raw mode (stdin sends \x03, not SIGINT)
tui.addInputListener((data: string) => {
  // Ctrl+C exits
  if (matchesKey(data, "ctrl+c") || data === "\x03") {
    shutdown();
    return { consume: true };
  }
  // ESC cancels the current agent turn
  if (matchesKey(data, "escape") && promptRunning) {
    agent.cancel();
    feed.addMessage({
      id: `cancel-${Date.now()}`,
      role: "system",
      text: "_Cancelled._",
    });
    setTimeout(() => tui.requestRender(), 0);
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

// Load ANSI logo from file — raw escape sequences, bypass markdown
const logoRaw = loadPrompt("logo.ans");
const logoLines = logoRaw
  ? logoRaw
      .replace(/\[\?25[lh]/g, "")  // strip cursor hide/show sequences
      .split("\n")
      .filter((l) => l.length > 0)
  : [];

feed.setPrefixLines([...logoLines, ""]);

// Detect first-run: check if any connections exist
const hasConnections = await (async () => {
  try {
    const resp = await fetch(`${BASE_URL}/api/connections/list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(2000),
    });
    const data = (await resp.json()) as { connections?: unknown[] };
    return (data.connections?.length ?? 0) > 0;
  } catch {
    return false;
  }
})();

const shouldRunFte = FORCE_FTE || !hasConnections;

if (shouldRunFte) {
  feed.addMessage({
    id: "welcome",
    role: "system",
    text: [
      "**db-mcp** by ApeLogic",
      "",
      "_Welcome! Let me help you get started..._",
    ].join("\n"),
  });
} else {
  feed.addMessage({
    id: "welcome",
    role: "system",
    text: [
      "**db-mcp** by ApeLogic",
      "",
      "Type a question to query your data. Type `/` for commands.",
      "_Press Ctrl+C to exit. ESC to cancel._",
    ].join("\n"),
  });
}

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
    case "tool_start": {
      const name = event.tool;
      let detail = name;
      // Try to extract a meaningful description from params (rawInput)
      if (event.params != null && typeof event.params === "object") {
        const p = event.params as Record<string, unknown>;
        const hint = p.command ?? p.query ?? p.sql ?? p.pattern ??
                     p.file_path ?? p.intent ?? p.connection ?? p.name;
        if (hint) {
          const s = String(hint).replace(/\n/g, " ").trim();
          detail = s.length > 60 ? `${name}: ${s.slice(0, 60)}…` : `${name}: ${s}`;
        }
      }
      feed.addMessage({
        id: `tool-${Date.now()}-${Math.random()}`,
        role: "tool",
        text: detail,
      });
      break;
    }
    case "tool_update": {
      feed.updateLastTool(event.detail);
      break;
    }
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
    case "usage":
      statusBar.updateUsage(event.usage);
      break;
    case "done":
      currentAssistantId = null;
      break;
  }
  // Schedule render on next tick — stream events arrive from child process I/O,
  // and the TUI render loop may not pick up requestRender() synchronously
  setTimeout(() => tui.requestRender(), 0);
}

// ---------------------------------------------------------------------------
// Input handling
// ---------------------------------------------------------------------------

let promptRunning = false;
const pendingMessages: string[] = [];

editor.onSubmit = async (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return;

  editor.setText("");
  editor.addToHistory(trimmed);

  if (trimmed.startsWith("/")) {
    await handleCommand(trimmed);
    tui.requestRender();
    return;
  }

  if (promptRunning) {
    // Queue as follow-up — will be sent after current turn completes
    pendingMessages.push(trimmed);
    feed.addMessage({
      id: `queued-${Date.now()}`,
      role: "user",
      text: `${trimmed}  _(queued)_`,
    });
    setTimeout(() => tui.requestRender(), 0);
    return;
  }

  await runPrompt(trimmed);
};

async function runPrompt(text: string): Promise<void> {
  promptRunning = true;
  try {
    await handlePrompt(text);
  } finally {
    promptRunning = false;
    feed.completeTurn();
    currentAssistantId = null;
    setTimeout(() => tui.requestRender(), 0);
  }

  // Process queued follow-up messages
  while (pendingMessages.length > 0) {
    const next = pendingMessages.shift()!;
    promptRunning = true;
    try {
      await handlePrompt(next);
    } finally {
      promptRunning = false;
      feed.completeTurn();
      currentAssistantId = null;
      setTimeout(() => tui.requestRender(), 0);
    }
  }
}

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

    // Onboarding commands
    case "/doctor":
      await runCli("db-mcp doctor");
      break;
    case "/env": {
      // Secure local secret storage — never sent to agent
      // Usage: /env <connection> <KEY> <value>
      const parts = arg.split(" ");
      if (parts.length < 3) {
        feed.addMessage({
          id: `env-err-${Date.now()}`, role: "error",
          text: "Usage: `/env <connection> <KEY> <value>`\nExample: `/env nova DATABASE_URL postgres://user:pass@host/db`",
        });
        break;
      }
      const [connName, key, ...valueParts] = parts;
      const value = valueParts.join(" ");
      try {
        const { mkdirSync, writeFileSync, readFileSync, existsSync } = await import("node:fs");
        const { homedir } = await import("node:os");
        const { join } = await import("node:path");
        const connDir = join(homedir(), ".db-mcp", "connections", connName!);
        mkdirSync(connDir, { recursive: true });
        const envFile = join(connDir, ".env");
        // Read existing .env, update or append the key
        let lines: string[] = [];
        if (existsSync(envFile)) {
          lines = readFileSync(envFile, "utf8").split("\n").filter(l => !l.startsWith(`${key}=`));
        }
        lines.push(`${key}=${value}`);
        writeFileSync(envFile, lines.filter(Boolean).join("\n") + "\n");
        feed.addMessage({
          id: `env-ok-${Date.now()}`, role: "system",
          text: `Secret \`${key}\` written to \`~/.db-mcp/connections/${connName}/.env\``,
        });
      } catch (err) {
        feed.addMessage({
          id: `env-fail-${Date.now()}`, role: "error",
          text: `Failed to write secret: ${err instanceof Error ? err.message : String(err)}`,
        });
      }
      break;
    }
    case "/playground":
      feed.addMessage({ id: `pg-${Date.now()}`, role: "system", text: "_Installing playground database..._" });
      tui.requestRender();
      await runCli("db-mcp playground install");
      await runCli("db-mcp use playground");
      await refreshStatus();
      feed.addMessage({
        id: `pg-done-${Date.now()}`,
        role: "system",
        text: "Playground ready! Try asking: _How many albums does each artist have?_",
      });
      break;
    case "/init":
      // Route to agent as a conversational onboarding flow
      await runPrompt(
        arg
          ? `I want to set up a new db-mcp connection called "${arg}". Guide me through it.`
          : "I want to set up a new db-mcp database connection. Ask me what database I use and help me configure it step by step."
      );
      break;

    // CLI commands — run db-mcp directly
    case "/connections":
      await runCli("db-mcp list");
      break;
    case "/use":
      if (!arg) { feed.addMessage({ id: `e-${Date.now()}`, role: "error", text: "Usage: /use CONNECTION_NAME" }); break; }
      await runCli(`db-mcp use ${arg}`);
      await refreshStatus();
      break;
    case "/schema":
      await runCli(arg ? `db-mcp schema ${arg}` : "db-mcp schema show");
      break;
    case "/rules":
      await runCli(arg ? `db-mcp rules ${arg}` : "db-mcp rules list");
      break;
    case "/examples":
      await runCli(arg ? `db-mcp examples ${arg}` : "db-mcp examples list");
      break;
    case "/metrics":
      await runCli(arg ? `db-mcp metrics ${arg}` : "db-mcp metrics list");
      break;
    case "/gaps":
      await runCli(arg ? `db-mcp gaps ${arg}` : "db-mcp gaps list");
      break;
    case "/sync":
      await runCli("db-mcp sync");
      break;
    case "/model":
      feed.addMessage({ id: `m-${Date.now()}`, role: "system", text: "Model selection requires an active agent session." });
      break;
    case "/session":
      feed.addMessage({
        id: `s-${Date.now()}`,
        role: "system",
        text: agent.sessionId
          ? `Session: ${agent.sessionId} · Agent: ${agent.commandName}`
          : "No active session. Type a question to start.",
      });
      break;

    default:
      feed.addMessage({
        id: `err-${Date.now()}`,
        role: "error",
        text: `Unknown command: ${cmd}`,
      });
  }
}

/** Run a db-mcp CLI command and show output in the feed. */
async function runCli(command: string): Promise<void> {
  const { handleCreateTerminal, handleTerminalOutput, handleReleaseTerminal } = await import("./acp/terminal.js");
  const [cmd, ...args] = command.split(" ");
  const { terminalId } = handleCreateTerminal({ command: cmd!, args });
  const result = await handleTerminalOutput({ terminalId });
  handleReleaseTerminal({ terminalId });

  let output = result.output.trim();
  if (output) {
    // Clean up CLI output for TUI context
    output = output
      .replace(/Restart (?:Claude Desktop|your MCP agent) to [\w ]+\.?\n?/g, "")
      .replace(/^[✓✗●] /gm, "")         // strip status bullets
      .replace(/'/g, "")                  // strip quotes around names
      .trim();
    if (output) {
      feed.addMessage({
        id: `cli-${Date.now()}`,
        role: "system",
        text: output,
      });
    }
  }
  if (result.exitStatus && result.exitStatus.exitCode !== 0 && result.exitStatus.exitCode !== 2) {
    // Exit code 2 = Click usage error (missing args) — the help output is already shown above
    feed.addMessage({
      id: `cli-err-${Date.now()}`,
      role: "error",
      text: `Exit code: ${result.exitStatus.exitCode}`,
    });
  }
  setTimeout(() => tui.requestRender(), 0);
}

async function handlePrompt(text: string): Promise<void> {
  feed.addMessage({
    id: `user-${Date.now()}`,
    role: "user",
    text,
  });

  // Auto-connect agent on first prompt
  if (!agent.connected) {
    // Preflight: check prerequisites before attempting connection
    const problem = await checkAgentPrerequisites();
    if (problem) {
      feed.addMessage({
        id: `preflight-${Date.now()}`,
        role: "error",
        text: problem,
      });
      tui.requestRender();
      return;
    }

    feed.addMessage({
      id: `connecting-${Date.now()}`,
      role: "system",
      text: `_Connecting to agent \`${agent.commandName}\`..._`,
    });
    tui.requestRender();

    try {
      await agent.connect(handleAgentEvent, statusBar.state.connection !== "none" ? statusBar.state.connection : undefined);
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
        text: `Failed to connect to agent: ${msg}`,
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
  // completeTurn + cleanup handled by runPrompt's finally block
}

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------

async function refreshStatus(): Promise<void> {
  try {
    const resp = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(2000) });
    statusBar.update({ healthy: resp.ok });

    // Get active connection
    const connResp = await fetch(`${BASE_URL}/api/connections/list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(2000),
    });
    const connData = (await connResp.json()) as { connections?: Array<{ name: string; isActive: boolean }> };
    const active = connData.connections?.find(c => c.isActive);
    statusBar.update({ connection: active?.name ?? "none" });
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

/** Reset terminal to normal state — must run even on crash. */
function resetTerminal(): void {
  try {
    process.stdout.write("\x1b[=0u");   // disable Kitty keyboard protocol
    process.stdout.write("\x1b[<u");    // pop Kitty stack
    process.stdout.write("\x1b[>0m");   // disable modifyOtherKeys
    process.stdout.write("\x1b[?25h");  // show cursor
    process.stdout.write("\x1b[?2004l"); // disable bracketed paste
  } catch {}
}

async function shutdown(): Promise<void> {
  clearInterval(pollInterval);
  // Reset terminal FIRST — before anything that could hang
  resetTerminal();
  try { tui.stop(); } catch {}
  try { await agent.disconnect(); } catch {}
  await terminal.drainInput(500, 100).catch(() => {});
  await new Promise(resolve => setTimeout(resolve, 100));
  process.exit(0);
}

// Ensure terminal is always reset, even on crash
process.on("exit", resetTerminal);
process.on("SIGINT", () => shutdown());
process.on("SIGTERM", () => shutdown());

// Initial status check, then start
refreshStatus().then(() => {
  tui.start();
  tui.requestRender();

  // Auto-trigger first-time experience.
  // Use editor.onSubmit to inject the prompt as if the user typed it —
  // this ensures the TUI render loop is fully active.
  if (shouldRunFte) {
    // Pre-fill the editor so the user just presses Enter to start
    const ftePrompt = loadPrompt("fte-trigger.md") || "Help me get started";
    editor.setText(ftePrompt);
  }
});
