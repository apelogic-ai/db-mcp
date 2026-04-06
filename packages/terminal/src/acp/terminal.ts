/**
 * Terminal executor for ACP — runs CLI commands requested by the agent.
 */
import { execFile } from "node:child_process";

interface TerminalState {
  command: string;
  args: string[];
  stdout: string;
  stderr: string;
  exitCode: number | null;
  done: boolean;
  promise: Promise<void>;
}

const terminals = new Map<string, TerminalState>();
let nextId = 1;

export function handleCreateTerminal(params: {
  command: string;
  args?: string[];
  cwd?: string;
  env?: Array<{ name: string; value: string }>;
  outputByteLimit?: number;
}): { terminalId: string } {
  const id = `term-${nextId++}`;
  const args = params.args ?? [];
  const env = params.env
    ? Object.fromEntries(params.env.map(e => [e.name, e.value]))
    : undefined;

  const state: TerminalState = {
    command: params.command,
    args,
    stdout: "",
    stderr: "",
    exitCode: null,
    done: false,
    promise: Promise.resolve(),
  };

  state.promise = new Promise<void>((resolve) => {
    const child = execFile(
      params.command,
      args,
      {
        cwd: params.cwd ?? undefined,
        env: (() => {
          // Strip daemon-inherited CONNECTION_NAME/CONNECTION_PATH/DATABASE_URL
          // so child CLI processes resolve the active connection from config.yaml
          // instead of using the daemon's startup connection.
          const base = { ...process.env };
          delete base.CONNECTION_NAME;
          delete base.CONNECTION_PATH;
          delete base.DATABASE_URL;
          return env ? { ...base, ...env } : base;
        })(),
        maxBuffer: params.outputByteLimit ?? 1024 * 1024,
        timeout: 60_000,
      },
      (error, stdout, stderr) => {
        state.stdout = stdout;
        state.stderr = stderr;
        state.exitCode = error?.code !== undefined
          ? (typeof error.code === "number" ? error.code : 1)
          : 0;
        state.done = true;
        resolve();
      },
    );

    child.on("exit", (code) => {
      if (state.exitCode === null) {
        state.exitCode = code ?? 0;
      }
    });
  });

  terminals.set(id, state);
  return { terminalId: id };
}

export async function handleTerminalOutput(params: {
  terminalId: string;
}): Promise<{ output: string; truncated: boolean; exitStatus?: { exitCode: number } }> {
  const state = terminals.get(params.terminalId);
  if (!state) {
    return { output: "Terminal not found", truncated: false, exitStatus: { exitCode: 1 } };
  }

  // Wait for command to finish
  await state.promise;

  const output = state.stderr
    ? `${state.stdout}\n${state.stderr}`
    : state.stdout;

  return {
    output,
    truncated: false,
    exitStatus: state.exitCode !== null ? { exitCode: state.exitCode } : undefined,
  };
}

export async function handleWaitForTerminalExit(params: {
  terminalId: string;
}): Promise<{ exitCode: number }> {
  const state = terminals.get(params.terminalId);
  if (!state) return { exitCode: 1 };
  await state.promise;
  return { exitCode: state.exitCode ?? 0 };
}

export function handleReleaseTerminal(params: {
  terminalId: string;
}): {} {
  terminals.delete(params.terminalId);
  return {};
}
