/**
 * Slash command definitions for the editor autocomplete.
 */
import type { SlashCommand } from "@mariozechner/pi-tui";

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "/help", description: "show help" },
  { name: "/clear", description: "clear the feed" },
  { name: "/status", description: "server status" },
  { name: "/connections", description: "list connections" },
  { name: "/use", description: "switch connection" },
  { name: "/schema", description: "show tables" },
  { name: "/rules", description: "list business rules" },
  { name: "/metrics", description: "list metrics" },
  { name: "/gaps", description: "list knowledge gaps" },
  { name: "/agent", description: "agent status" },
  { name: "/model", description: "set agent model" },
  { name: "/quit", description: "exit" },
];
