/**
 * StatusBar component — single line at the bottom showing connection, health, tokens.
 */
import type { Component } from "@mariozechner/pi-tui";
import chalk from "chalk";

export interface StatusState {
  connection: string;
  healthy: boolean;
  agent: string;
  agentConnected: boolean;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export class StatusBar implements Component {
  state: StatusState = {
    connection: "none",
    healthy: false,
    agent: "",
    agentConnected: false,
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
  };

  update(partial: Partial<StatusState>): void {
    Object.assign(this.state, partial);
  }

  addUsage(usage: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number }): void {
    this.state.inputTokens += usage.input_tokens ?? 0;
    this.state.outputTokens += usage.output_tokens ?? 0;
    this.state.cacheReadTokens += usage.cache_read_input_tokens ?? 0;
  }

  invalidate(): void {}

  render(width: number): string[] {
    const health = this.state.healthy
      ? chalk.green("●")
      : chalk.red("●");
    const conn = this.state.connection || "none";

    const parts = [`${health} ${conn}`];

    if (this.state.agent) {
      const dot = this.state.agentConnected ? chalk.green("●") : chalk.dim("○");
      parts.push(`${dot} ${this.state.agent}`);
    }

    const totalTokens = this.state.inputTokens + this.state.outputTokens;
    if (totalTokens > 0) {
      const tokStr = `↑${formatTokens(this.state.inputTokens)} ↓${formatTokens(this.state.outputTokens)}`;
      if (this.state.cacheReadTokens > 0) {
        parts.push(`${tokStr} (${formatTokens(this.state.cacheReadTokens)} cached)`);
      } else {
        parts.push(tokStr);
      }
    }

    const line = parts.join("  │  ");
    const pad = Math.max(0, width - visibleLen(line));
    return [chalk.bgGray.white(line + " ".repeat(pad))];
  }
}

function visibleLen(str: string): number {
  return str.replace(/\x1b\[[0-9;]*m/g, "").length;
}
