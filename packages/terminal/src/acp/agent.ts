/**
 * ACP agent session — wraps @nexus/acp-bridge for the TUI.
 *
 * Spawns an ACP-compatible agent (e.g. claude-agent-acp), creates a session
 * with the db-mcp MCP server, and streams responses back to the feed.
 */
import { spawnAgent, type AgentProcess } from "@nexus/acp-bridge";
import { createAcpSession, type AcpSession } from "@nexus/acp-bridge";
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
  | { type: "usage"; usage: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number } }
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
  async connect(onEvent: (event: AgentEvent) => void): Promise<void> {
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

    // Create a session with our MCP server
    const sessionResult = await this.process.rpc.sendRequest("session/new", {
      cwd: process.cwd(),
      mcpServers: [{
        name: "db-mcp",
        type: "http",
        url: this.config.mcpUrl.endsWith("/") ? this.config.mcpUrl : this.config.mcpUrl + "/",
        headers: [],
      }],
      _meta: {
        systemPrompt: [
          "You are a database assistant powered by db-mcp CLI.",
          "",
          "Use the `db-mcp` CLI for ALL database operations. Key commands:",
          "  db-mcp list                    — list connections",
          "  db-mcp use <name>              — switch active connection",
          "  db-mcp status                  — show current config",
          "  db-mcp query '<question>'      — query in natural language",
          "  db-mcp schema                  — show tables and columns",
          "  db-mcp examples                — list training examples",
          "  db-mcp rules                   — list business rules",
          "  db-mcp metrics                 — list metrics catalog",
          "  db-mcp gaps                    — list knowledge gaps",
          "",
          "When the user mentions a connection name, run `db-mcp use <name>` first.",
          "For SQL queries, use `db-mcp query` which handles schema lookup, SQL generation, and execution.",
          "Run `db-mcp --help` to see all available commands.",
        ].join("\n"),
      },
    }) as { sessionId: string };

    this._sessionId = sessionResult.sessionId;

    // Handle all incoming RPC requests from the agent
    this.process.rpc.onRequest(async (method: string, params: unknown) => {
      // Auto-approve ALL tool calls with allow_always
      // Also extract tool call details for display
      if (method === "session/request_permission") {
        const p = params as {
          toolCall?: { title?: string; rawInput?: unknown };
        } | undefined;
        if (p?.toolCall?.rawInput && this._onEvent) {
          // Emit a richer tool_start with actual params
          const input = p.toolCall.rawInput as Record<string, unknown>;
          const toolName = p.toolCall.title ?? "unknown";
          this._onEvent({
            type: "tool_start",
            tool: toolName,
            params: input,
          });
        }
        return { outcome: { outcome: "selected", optionId: "allow_always" } };
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

    // Capture usage_update notifications (dropped by the bridge)
    this.process.rpc.onNotification((notification) => {
      if (notification.method !== "session/update") return;
      const p = notification.params as { update?: Record<string, unknown> } | undefined;
      if (p?.update?.sessionUpdate === "usage_update") {
        const { appendFileSync } = require("node:fs");
        appendFileSync("/tmp/db-mcp-usage.log", JSON.stringify(p.update) + "\n");
        // Extract usage from whichever field contains it
        const u = (p.update.usage ?? p.update) as Record<string, unknown>;
        const usage = {
          input_tokens: Number(u.input_tokens ?? u.inputTokens ?? 0),
          output_tokens: Number(u.output_tokens ?? u.outputTokens ?? 0),
          cache_read_input_tokens: Number(u.cache_read_input_tokens ?? u.cacheReadInputTokens ?? 0),
        };
        if (usage.input_tokens || usage.output_tokens) {
          onEvent({ type: "usage", usage });
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
        case "tool_start":
          // Skip — tool_call notifications have empty params.
          // We emit tool_start from request_permission instead (has rawInput).
          break;
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
