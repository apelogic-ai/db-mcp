import { spawn, type ChildProcess } from "node:child_process";
import { createRpcClient, type RpcClient } from "./rpc.js";

export interface AgentProcess {
  rpc: RpcClient;
  process: ChildProcess;
  isAlive: () => boolean;
  kill: () => Promise<void>;
  onExit: (handler: (code: number | null) => void) => void;
}

export const spawnAgent = (
  command: string[],
  options?: { cwd?: string; env?: Record<string, string>; timeout?: number },
): AgentProcess => {
  const [cmd, ...args] = command;
  const child = spawn(cmd!, args, {
    stdio: ["pipe", "pipe", "pipe"],
    cwd: options?.cwd,
    env: options?.env ? { ...process.env, ...options.env } : undefined,
  });

  // Forward agent stderr to gateway console for debugging
  child.stderr?.on("data", (chunk: Buffer) => {
    process.stderr.write(`[agent] ${chunk.toString()}`);
  });

  const rpc = createRpcClient(child.stdout!, child.stdin!, {
    timeout: options?.timeout,
  });

  let alive = true;

  child.on("close", () => {
    alive = false;
  });

  const isAlive = (): boolean => alive;

  const kill = (): Promise<void> =>
    new Promise<void>((resolve) => {
      if (!alive) {
        resolve();
        return;
      }
      child.once("close", () => resolve());
      child.kill("SIGTERM");
    });

  const onExit = (handler: (code: number | null) => void): void => {
    child.on("close", handler);
  };

  return { rpc, process: child, isAlive, kill, onExit };
};
