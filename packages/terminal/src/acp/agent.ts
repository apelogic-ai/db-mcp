/**
 * ACP agent session — wraps @nexus/acp-bridge for the TUI.
 *
 * Spawns an ACP-compatible agent (e.g. claude-agent-acp), creates a session
 * with the db-mcp MCP server, and streams responses back to the feed.
 */
import { spawnAgent, type AgentProcess } from "@nexus/acp-bridge";
import { createAcpSession, type AcpSession } from "@nexus/acp-bridge";

/** Events emitted to the TUI during a prompt. */
export type AgentEvent =
  | { type: "text_delta"; delta: string }
  | { type: "thinking_delta"; delta: string }
  | { type: "tool_start"; tool: string; params?: unknown }
  | { type: "tool_end"; tool: string; result?: string }
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

    // Spawn the agent process
    try {
      this.process = spawnAgent(this.config.command, {
        timeout: 60_000,
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
          "You are a database assistant connected to db-mcp.",
          "Use the db-mcp MCP tools (shell, run_sql, validate_sql, list_connections, etc.) for ALL database operations.",
          "Do NOT use Terminal or Bash tools — they are not available in this environment.",
          "Start by calling the db-mcp shell tool with command='cat PROTOCOL.md' to learn the available operations.",
        ].join("\n"),
      },
    }) as { sessionId: string };

    this._sessionId = sessionResult.sessionId;

    // Handle terminal and file requests from the agent (reject gracefully)
    this.process.rpc.onRequest(async (method: string, _params: unknown) => {
      if (method === "create_terminal" || method === "kill_terminal" ||
          method === "wait_for_terminal_exit" || method === "release_terminal") {
        throw new Error("Terminal not available in TUI mode. Use MCP tools instead.");
      }
      if (method === "read_text_file" || method === "write_text_file") {
        throw new Error("File operations not available in TUI mode. Use MCP tools instead.");
      }
      throw new Error(`Unsupported method: ${method}`);
    });

    // Create the ACP session wrapper that translates notifications → events
    // Policy: auto-allow all tool calls (the daemon handles authorization)
    this.session = createAcpSession(
      this.process.rpc,
      this._sessionId,
      this._sessionId,
      {
        policyEvaluator: () => "allow",
      },
    );

    this.session.onEvent((gatewayEvent) => {
      switch (gatewayEvent.type) {
        case "text_delta":
          onEvent({ type: "text_delta", delta: (gatewayEvent as { delta: string }).delta });
          break;
        case "thinking_delta":
          onEvent({ type: "thinking_delta", delta: (gatewayEvent as { delta: string }).delta });
          break;
        case "tool_start": {
          const ev = gatewayEvent as { tool: string; params?: unknown };
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
    await this.session.prompt(text);
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
