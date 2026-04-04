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
  | { type: "tool_start"; tool: string }
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
    return this.config.command[0] ?? "unknown";
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
        url: this.config.mcpUrl,
        headers: [],
      }],
    }) as { sessionId: string };

    this._sessionId = sessionResult.sessionId;

    // Create the ACP session wrapper that translates notifications → events
    this.session = createAcpSession(
      this.process.rpc,
      this._sessionId,
      this._sessionId,
    );

    this.session.onEvent((gatewayEvent) => {
      switch (gatewayEvent.type) {
        case "text_delta":
          onEvent({ type: "text_delta", delta: (gatewayEvent as { delta: string }).delta });
          break;
        case "thinking_delta":
          onEvent({ type: "thinking_delta", delta: (gatewayEvent as { delta: string }).delta });
          break;
        case "tool_start":
          onEvent({ type: "tool_start", tool: (gatewayEvent as { tool: string }).tool });
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
