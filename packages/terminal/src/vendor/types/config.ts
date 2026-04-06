// Config types

export interface RuntimeProfile {
  command: string[];
  cwd?: string;
  env?: Record<string, string>;
  defaultModel?: string;
}

export interface MemoryConfig {
  enabled?: boolean;
  provider?: "sqlite";
  contextBudgetTokens?: number;
  hotMessageCount?: number;
  warmSummaryCount?: number;
  coldFactCount?: number;
  workspaceSummaryCount?: number;
  workspaceFactCount?: number;
  maxFactsPerTurn?: number;
  maxFactLength?: number;
  summaryWindowMessages?: number;
}

export interface ChannelBaseConfig {
  kind: "telegram" | "discord";
  enabled?: boolean;
  runtimeId?: string;
  model?: string;
  workspaceId?: string;
  typingIndicator?: boolean;
  streamingMode?: "off" | "edit";
  steeringMode?: "off" | "on";
}

export interface TelegramChannelConfig extends ChannelBaseConfig {
  kind: "telegram";
  botToken: string;
  apiBaseUrl?: string;
  pollTimeoutSeconds?: number;
  pollIntervalMs?: number;
  allowedChatIds?: string[];
}

export interface DiscordChannelConfig extends ChannelBaseConfig {
  kind: "discord";
  botToken: string;
  applicationId?: string;
  guildId?: string;
  allowedUserIds?: string[];
}

export type ChannelConfig =
  | TelegramChannelConfig
  | DiscordChannelConfig;

export interface NexusConfig {
  port: number;
  host: string;
  auth: { token: string };
  runtime?: RuntimeProfile;
  runtimes?: Record<string, RuntimeProfile>;
  defaultRuntimeId?: string;
  modelRouting?: Record<string, string>;
  modelAliases?: Record<string, string>;
  modelCatalog?: Record<string, string[]>;
  workspaceDefaultId?: string;
  sessionIdleTimeoutMs?: number;
  sessionSweepIntervalMs?: number;
  wsPingIntervalMs?: number;
  wsPongGraceMs?: number;
  runtimeRestartMaxAttempts?: number;
  runtimeRestartBaseDelayMs?: number;
  runtimeRestartMaxDelayMs?: number;
  memory?: MemoryConfig;
  channels?: Record<string, ChannelConfig>;
  dataDir: string;
}
