/**
 * Slash command definitions with dynamic argument completions.
 */
import type { SlashCommand, AutocompleteItem } from "@mariozechner/pi-tui";

/** Build slash commands with dynamic completions from the daemon. */
export function buildSlashCommands(baseUrl: string): SlashCommand[] {
  // Cache connection list (refreshed on each completion request)
  async function fetchConnections(): Promise<AutocompleteItem[]> {
    try {
      const resp = await fetch(`${baseUrl}/api/connections/list`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
        signal: AbortSignal.timeout(2000),
      });
      const data = (await resp.json()) as {
        connections?: Array<{ name: string; isActive: boolean }>;
      };
      return (data.connections ?? []).map((c) => ({
        value: c.name,
        label: c.name,
        description: c.isActive ? "active" : undefined,
      }));
    } catch {
      return [];
    }
  }

  function filterByPrefix(
    items: AutocompleteItem[],
    prefix: string,
  ): AutocompleteItem[] {
    if (!prefix) return items;
    const lower = prefix.toLowerCase();
    return items.filter((i) => i.value.toLowerCase().startsWith(lower));
  }

  return [
    { name: "help", description: "show help" },
    { name: "clear", description: "clear the feed" },
    { name: "status", description: "server status" },
    { name: "doctor", description: "run connection health checks" },
    {
      name: "env",
      description: "securely store a secret (not shared with agent)",
      async getArgumentCompletions(prefix) {
        // First arg = connection name
        if (!prefix.includes(" ")) {
          return filterByPrefix(await fetchConnections(), prefix);
        }
        // Second arg = common key names
        const parts = prefix.split(" ");
        if (parts.length === 2) {
          const keys = [
            { value: "DATABASE_URL", label: "DATABASE_URL", description: "database connection string" },
            { value: "API_KEY", label: "API_KEY", description: "API authentication key" },
            { value: "API_TOKEN", label: "API_TOKEN", description: "API bearer token" },
          ];
          return filterByPrefix(keys, parts[1]!);
        }
        return null;
      },
    },
    {
      name: "use",
      description: "switch connection",
      async getArgumentCompletions(prefix) {
        return filterByPrefix(await fetchConnections(), prefix);
      },
    },
    { name: "connections", description: "list connections" },
    { name: "playground", description: "install sample database" },
    { name: "init", description: "set up a new connection" },
    {
      name: "schema",
      description: "show tables",
      getArgumentCompletions(prefix) {
        const subs = [
          { value: "show", label: "show", description: "table/column descriptions" },
          { value: "tables", label: "tables", description: "list tables" },
          { value: "describe", label: "describe", description: "describe a table" },
          { value: "sample", label: "sample", description: "sample rows" },
        ];
        return filterByPrefix(subs, prefix);
      },
    },
    {
      name: "rules",
      description: "list business rules",
      getArgumentCompletions(prefix) {
        const subs = [
          { value: "list", label: "list", description: "list all rules" },
          { value: "add", label: "add", description: "add a rule" },
        ];
        return filterByPrefix(subs, prefix);
      },
    },
    {
      name: "examples",
      description: "list query examples",
      getArgumentCompletions(prefix) {
        const subs = [
          { value: "list", label: "list", description: "list all examples" },
          { value: "search", label: "search", description: "search by keyword" },
        ];
        return filterByPrefix(subs, prefix);
      },
    },
    {
      name: "metrics",
      description: "list metrics",
      getArgumentCompletions(prefix) {
        const subs = [
          { value: "list", label: "list", description: "list all metrics" },
          { value: "add", label: "add", description: "add a metric" },
          { value: "discover", label: "discover", description: "discover candidates" },
        ];
        return filterByPrefix(subs, prefix);
      },
    },
    {
      name: "gaps",
      description: "list knowledge gaps",
      getArgumentCompletions(prefix) {
        const subs = [
          { value: "list", label: "list", description: "list open gaps" },
          { value: "dismiss", label: "dismiss", description: "dismiss a gap" },
        ];
        return filterByPrefix(subs, prefix);
      },
    },
    { name: "sync", description: "sync vault with git" },
    { name: "agent", description: "agent status" },
    { name: "session", description: "show session info" },
    { name: "quit", description: "exit" },
  ];
}
