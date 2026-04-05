/**
 * StatusBar component — single line: connection, agent, context usage, cost.
 */
import type { Component } from "@mariozechner/pi-tui";
import chalk from "chalk";

export interface StatusState {
  connection: string;
  healthy: boolean;
  agent: string;
  agentConnected: boolean;
  contextUsed: number;
  contextSize: number;
  cost: number;
  currency: string;
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
    contextUsed: 0,
    contextSize: 0,
    cost: 0,
    currency: "USD",
  };

  update(partial: Partial<StatusState>): void {
    Object.assign(this.state, partial);
  }

  updateUsage(usage: { used: number; size: number; cost: number; currency: string }): void {
    this.state.contextUsed = usage.used;
    this.state.contextSize = usage.size;
    this.state.cost += usage.cost;
    this.state.currency = usage.currency;
  }

  invalidate(): void {}

  render(width: number): string[] {
    const health = this.state.healthy ? chalk.green("●") : chalk.red("●");
    const conn = this.state.connection || "none";
    const parts = [` ${health} ${conn}`];

    if (this.state.agent) {
      const dot = this.state.agentConnected ? chalk.green("●") : chalk.dim("○");
      parts.push(`${dot} ${this.state.agent}`);
    }

    if (this.state.contextUsed > 0) {
      const pct = Math.round((this.state.contextUsed / this.state.contextSize) * 100);
      parts.push(`ctx ${formatTokens(this.state.contextUsed)}/${formatTokens(this.state.contextSize)} (${pct}%)`);
    }

    if (this.state.cost > 0) {
      parts.push(`$${this.state.cost.toFixed(2)}`);
    }

    const line = parts.join("  │  ");
    const pad = Math.max(0, width - visibleLen(line));
    return [chalk.bgGray.white(line + " ".repeat(pad))];
  }
}

function visibleLen(str: string): number {
  return str.replace(/\x1b\[[0-9;]*m/g, "").length;
}
