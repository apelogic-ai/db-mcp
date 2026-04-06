/**
 * ACP agent session — wraps @nexus/acp-bridge for the TUI.
 *
 * Spawns an ACP-compatible agent (e.g. claude-agent-acp), creates a session
 * with the db-mcp MCP server, and streams responses back to the feed.
 */
import { spawnAgent, type AgentProcess } from "../vendor/acp-bridge/index.js";
import { createAcpSession, type AcpSession } from "../vendor/acp-bridge/index.js";
import {
  handleCreateTerminal,
  handleTerminalOutput,
  handleWaitForTerminalExit,
  handleReleaseTerminal,
} from "./terminal.js";

/** Events emitted to the TUI during a prompt. */
export type AgentEvent =
  | { type: "text_delta"; delta: string }
  | { type: "thinking_delta"; delta: string }
  | { type: "tool_start"; tool: string; params?: unknown }
  | { type: "tool_end"; tool: string; result?: string }
  | { type: "tool_update"; detail: string }
  | { type: "usage"; usage: { used: number; size: number; cost: number; currency: string } }
  | { type: "error"; message: string }
  | { type: "done" };

export interface AgentConfig {
  /** ACP agent command, e.g. ["claude-agent-acp"] */
  command: string[];
  /** db-mcp MCP server URL, e.g. "http://localhost:8080/mcp" */
  mcpUrl: string;
}

export class Agent {
  private config: AgentConfig;
  private process: AgentProcess | null = null;
  private session: AcpSession | null = null;
  private _sessionId: string | null = null;
  private _onEvent: ((event: AgentEvent) => void) | null = null;

  constructor(config: AgentConfig) {
    this.config = config;
  }

  get connected(): boolean {
    return this.session !== null;
  }

  get sessionId(): string | null {
    return this._sessionId;
  }

  get commandName(): string {
    const cmd = this.config.command[0] ?? "unknown";
    return cmd.split("/").pop() ?? cmd;
  }

  /** Connect to the agent — spawn process, initialize, create session. */
  async connect(onEvent: (event: AgentEvent) => void, activeConnection?: string): Promise<void> {
    if (this.process) {
      throw new Error("Already connected");
    }
    this._onEvent = onEvent;

    // Spawn the agent process
    try {
      this.process = spawnAgent(this.config.command, {
        timeout: 300_000,  // 5min — prompts can take a while
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Could not start agent "${this.config.command.join(" ")}": ${msg}\n` +
        `Install with: npm i -g @agentclientprotocol/claude-agent-acp`
      );
    }

    // Route agent stderr to a file for debugging (not to terminal)
    const { createWriteStream } = await import("node:fs");
    const logStream = createWriteStream("/tmp/db-mcp-agent.log", { flags: "a" });
    this.process.process.stderr?.removeAllListeners("data");
    this.process.process.stderr?.on("data", (chunk: Buffer) => {
      logStream.write(chunk);
    });

    // Handle spawn errors (e.g. ENOENT after async start)
    await new Promise<void>((resolve, reject) => {
      const proc = this.process!.process;
      const onError = (err: Error) => {
        cleanup();
        this.process = null;
        reject(new Error(
          `Could not start agent "${this.config.command.join(" ")}": ${err.message}\n` +
          `Install with: npm i -g @agentclientprotocol/claude-agent-acp`
        ));
      };
      const onSpawn = () => { cleanup(); resolve(); };
      const cleanup = () => {
        proc.removeListener("error", onError);
        proc.removeListener("spawn", onSpawn);
      };
      proc.once("error", onError);
      proc.once("spawn", onSpawn);
    });

    this.process.onExit((code) => {
      onEvent({ type: "error", message: `Agent exited with code ${code}` });
      this.process = null;
      this.session = null;
      this._sessionId = null;
    });

    // Initialize the ACP connection
    const initResult = await this.process.rpc.sendRequest("initialize", {
      protocolVersion: 1,
      clientInfo: { name: "db-mcp-tui", version: "0.1.0" },
    }) as { protocolVersion: number };

    // Create a session — agent uses db-mcp CLI (no MCP server needed)
    const sessionResult = await this.process.rpc.sendRequest("session/new", {
      cwd: process.cwd(),
      mcpServers: [],
      _meta: {
        systemPrompt: [
          "You are a database operations assistant powered by the db-mcp CLI.",
          "You help users query data, onboard connections, troubleshoot, and manage their knowledge vault.",
          "",
          "## ANSWERING DATA QUESTIONS (SQL queries)",
          "When the user asks a question about data, YOU write the SQL:",
          "1. db-mcp rules list                   — check business rules FIRST",
          "2. db-mcp examples search --grep '<keyword>' — find similar query patterns",
          "3. db-mcp schema show | grep -A20 '<table>' — check columns for relevant tables",
          "4. Write SQL yourself based on rules, examples, and schema.",
          "5. db-mcp query run --confirmed '<SQL>' — execute your SQL",
          "Do NOT delegate SQL generation. YOU are the analyst.",
          "",
          "## ALL COMMANDS",
          "## SETTING UP A NEW CONNECTION",
          "When the user wants to connect a database, do NOT run `db-mcp init` (it is interactive).",
          "Instead, create the connection manually:",
          "1. Ask the user for: connection name, database type (postgres/mysql/clickhouse/trino), and DATABASE_URL",
          "2. mkdir -p ~/.db-mcp/connections/<name>",
          "3. echo 'DATABASE_URL=<url>' > ~/.db-mcp/connections/<name>/.env",
          "4. db-mcp use <name>",
          "5. db-mcp doctor — verify the connection works",
          "6. db-mcp discover — introspect the schema",
          "If doctor fails, help the user fix the URL.",
          "",
          "Connection management:",
          "  db-mcp list                          — list connections",
          "  db-mcp status                        — show active connection + config",
          "  db-mcp use <name>                    — switch connection",
          "  db-mcp doctor                        — preflight checks for a connection",
          "  db-mcp edit                          — edit connection credentials",
          "",
          "Schema & discovery:",
          "  db-mcp schema show                   — table/column descriptions from vault",
          "  db-mcp schema show | grep -A20 '<table>' — columns for one table",
          "  db-mcp schema tables                 — list tables in database",
          "  db-mcp schema sample <table>         — sample rows",
          "  db-mcp discover                      — introspect database schema",
          "  db-mcp domain show                   — view semantic domain model",
          "",
          "Querying:",
          "  db-mcp query run --confirmed '<SQL>' — execute SQL",
          "  db-mcp query validate '<SQL>'        — validate SQL without executing",
          "",
          "Knowledge vault:",
          "  db-mcp rules list                    — list business rules",
          "  db-mcp rules add '<rule>'            — add a business rule",
          "  db-mcp examples list                 — list query examples",
          "  db-mcp examples search --grep '<keyword>' — search examples by intent/SQL",
          "  db-mcp examples add                  — add a query example",
          "  db-mcp gaps list                     — list knowledge gaps",
          "  db-mcp gaps dismiss '<term>'         — dismiss a gap",
          "  db-mcp metrics list                  — list business metrics",
          "  db-mcp metrics add                   — add a metric",
          "  db-mcp metrics discover              — discover metric candidates",
          "",
          "Collaboration:",
          "  db-mcp sync                          — sync vault with git",
          "  db-mcp pull                          — pull vault from git",
          "  db-mcp git-init                      — enable git sync",
          "",
          "## RULES",
          "- Do NOT use mcp__* tools or ToolSearch. Use the db-mcp CLI commands above.",
          "- Do NOT run --help. Everything you need is above.",
          "- If a command fails, check `db-mcp status` then `db-mcp use <name>`.",
          "- When the user mentions a connection name, run `db-mcp use <name>` first.",
          "- Be CONCISE. Present results directly. No narration or 'Let me...' preamble.",
          ...(activeConnection
            ? [``, `## ACTIVE CONNECTION`, `The active connection is "${activeConnection}". Run \`db-mcp use ${activeConnection}\` as your first command.`]
            : []),
        ].join("\n"),
      },
    }) as { sessionId: string };

    this._sessionId = sessionResult.sessionId;

    // Handle all incoming RPC requests from the agent
    this.process.rpc.onRequest(async (method: string, params: unknown) => {
      // Auto-approve tool calls with allow_once (not allow_always!)
      // allow_once ensures we get a permission request for EVERY tool call,
      // which lets us extract the command details for display.
      if (method === "session/request_permission") {
        const p = params as {
          sessionId?: string;
          toolCall?: { title?: string; rawInput?: unknown; kind?: string; toolCallId?: string };
          options?: Array<{ optionId: string; name: string; kind: string }>;
        } | undefined;

        if (p?.toolCall?.rawInput && this._onEvent) {
          const input = p.toolCall.rawInput as Record<string, unknown>;
          const cmd = input.command ?? input.query ?? input.sql ?? input.pattern ?? input.file_path;
          if (cmd) {
            const s = String(cmd).replace(/\n/g, " ").trim();
            const detail = s.length > 80 ? `${s.slice(0, 80)}…` : s;
            this._onEvent({ type: "tool_update", detail });
          }
        }

        // Use "allow" (per-call approval) to get permission requests for every tool call.
        // The agent's options are: allow_always, allow, reject.
        // "allow_once" is NOT a valid optionId — it was causing intermittent rejections.
        return { outcome: { outcome: "selected", optionId: "allow" } };
      }
      // Terminal operations — execute CLI commands
      if (method === "create_terminal") {
        return handleCreateTerminal(params as any);
      }
      if (method === "terminal_output") {
        return await handleTerminalOutput(params as any);
      }
      if (method === "wait_for_terminal_exit") {
        return await handleWaitForTerminalExit(params as any);
      }
      if (method === "release_terminal" || method === "kill_terminal") {
        return handleReleaseTerminal(params as any);
      }
      // File operations — not supported in TUI
      if (method === "read_text_file" || method === "write_text_file") {
        throw new Error("File operations not available in TUI mode.");
      }
      throw new Error(`Unsupported method: ${method}`);
    });

    // Create the ACP session wrapper that translates notifications → events
    this.session = createAcpSession(
      this.process.rpc,
      this._sessionId,
      this._sessionId,
    );

    // Capture notifications dropped by the bridge (usage, tool_call details)
    this.process.rpc.onNotification((notification) => {
      if (notification.method !== "session/update") return;
      const p = notification.params as { update?: Record<string, unknown> } | undefined;
      if (!p?.update) return;
      const su = p.update.sessionUpdate;

      if (su === "usage_update") {
        const { appendFileSync } = require("node:fs");
        appendFileSync("/tmp/db-mcp-usage.log", JSON.stringify(p.update) + "\n");
        const u = p.update as Record<string, unknown>;
        const cost = u.cost as { amount?: number; currency?: string } | undefined;
        onEvent({
          type: "usage",
          usage: {
            used: Number(u.used ?? 0),
            size: Number(u.size ?? 0),
            cost: cost?.amount ?? 0,
            currency: (cost?.currency as string) ?? "USD",
          },
        });
        return;
      }

      // Extract tool details from tool_call / tool_call_update notifications.
      // The bridge drops intermediate tool_call_update notifications (only handles
      // completed/failed), and tool_call notifications arrive with empty rawInput.
      // This handler runs AFTER createAcpSession's handler, so the tool_start event
      // has already been emitted — we can safely emit tool_update to enrich it.
      if (su === "tool_call" || su === "tool_call_update") {
        const raw = p.update.rawInput as Record<string, unknown> | undefined;
        if (raw && this._onEvent) {
          const cmd = raw.command ?? raw.query ?? raw.sql ?? raw.pattern ??
                      raw.file_path ?? raw.intent ?? raw.connection ?? raw.name;
          if (cmd) {
            const s = String(cmd).replace(/\n/g, " ").trim();
            const detail = s.length > 80 ? `${s.slice(0, 80)}…` : s;
            this._onEvent({ type: "tool_update", detail });
          }
        }
      }
    });

    this.session.onEvent((gatewayEvent) => {
      switch (gatewayEvent.type) {
        case "text_delta":
          onEvent({ type: "text_delta", delta: (gatewayEvent as { delta: string }).delta });
          break;
        case "thinking_delta":
          onEvent({ type: "thinking_delta", delta: (gatewayEvent as { delta: string }).delta });
          break;
        case "tool_start": {
          // Emit with whatever info we have (params may be empty)
          const ev = gatewayEvent as { tool: string; params?: unknown; toolCallId?: string };
          onEvent({ type: "tool_start", tool: ev.tool, params: ev.params });
          break;
        }
        case "tool_end":
          onEvent({
            type: "tool_end",
            tool: (gatewayEvent as { tool: string }).tool,
            result: (gatewayEvent as { result?: string }).result,
          });
          break;
      }
    });
  }

  /** Send a prompt to the agent. Resolves when the agent finishes. */
  async prompt(text: string): Promise<void> {
    if (!this.session) {
      throw new Error("Not connected — call connect() first");
    }
    if (!this.process?.isAlive()) {
      throw new Error("Agent process is no longer running");
    }
    await this.session.prompt(text);
  }

  get alive(): boolean {
    return this.process?.isAlive() ?? false;
  }

  /** Cancel the current prompt. */
  cancel(): void {
    if (this.session) {
      this.session.cancel();
    }
  }

  /** Disconnect and kill the agent process. */
  async disconnect(): Promise<void> {
    if (this.process) {
      await this.process.kill();
      this.process = null;
      this.session = null;
      this._sessionId = null;
    }
  }
}
