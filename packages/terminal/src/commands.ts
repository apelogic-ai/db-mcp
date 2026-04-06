/**
 * Slash command definitions for the editor autocomplete.
 */
import type { SlashCommand } from "@mariozechner/pi-tui";

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "help", description: "show help" },
  { name: "clear", description: "clear the feed" },
  { name: "status", description: "server status" },
  { name: "doctor", description: "run connection health checks" },
  { name: "env", description: "securely store a secret (not shared with agent)" },
  { name: "connections", description: "list connections" },
  { name: "use", description: "switch connection" },
  { name: "playground", description: "install sample database" },
  { name: "init", description: "set up a new connection" },
  { name: "schema", description: "show tables" },
  { name: "rules", description: "list business rules" },
  { name: "examples", description: "list query examples" },
  { name: "metrics", description: "list metrics" },
  { name: "gaps", description: "list knowledge gaps" },
  { name: "sync", description: "sync vault with git" },
  { name: "agent", description: "agent status" },
  { name: "session", description: "show session info" },
  { name: "quit", description: "exit" },
];
