/**
 * StatusBar component — single line at the bottom showing connection + health.
 */
import type { Component } from "@mariozechner/pi-tui";
import chalk from "chalk";

export interface StatusState {
  connection: string;
  healthy: boolean;
  agent: string;
  agentConnected: boolean;
}

export class StatusBar implements Component {
  private state: StatusState = {
    connection: "none",
    healthy: false,
    agent: "",
    agentConnected: false,
  };

  update(state: Partial<StatusState>): void {
    Object.assign(this.state, state);
  }

  invalidate(): void {}

  render(width: number): string[] {
    const health = this.state.healthy
      ? chalk.green("●")
      : chalk.red("●");
    const conn = this.state.connection || "none";

    const parts = [`${health} ${conn}`];

    if (this.state.agent) {
      const agentStatus = this.state.agentConnected
        ? chalk.green("●")
        : chalk.dim("○");
      parts.push(`${agentStatus} ${this.state.agent}`);
    }

    const line = parts.join("  │  ");
    const pad = Math.max(0, width - visibleLen(line));
    return [chalk.bgGray.white(line + " ".repeat(pad))];
  }
}

function visibleLen(str: string): number {
  // Strip ANSI codes for length calculation
  return str.replace(/\x1b\[[0-9;]*m/g, "").length;
}
