/**
 * Config — load and merge ~/.miner/config.yaml with defaults.
 */

import { existsSync, readFileSync } from "node:fs";
import YAML from "yaml";
import type { DisclosureLevel } from "./types";

export interface MinerConfig {
  sources: {
    claude_code: boolean;
    codex: boolean;
    cursor: boolean;
  };
  ship: {
    endpoint: string | null;
    redactSecrets: boolean;
    schedule: "realtime" | "hourly" | "daily";
    disclosure: DisclosureLevel;
    anonymize: boolean;
  };
  privacy: {
    excludeProjects: string[];
  };
  pollIntervalMs: number;
  developer: string | null;
  machine: string | null;
}

export const DEFAULT_CONFIG: MinerConfig = {
  sources: {
    claude_code: true,
    codex: true,
    cursor: true,
  },
  ship: {
    endpoint: null,
    redactSecrets: true,
    schedule: "hourly",
    disclosure: "basic" as DisclosureLevel,
    anonymize: false,
  },
  privacy: {
    excludeProjects: [],
  },
  pollIntervalMs: 300_000, // 5 minutes
  developer: null,
  machine: null,
};

/**
 * Load config from a YAML file, merging with defaults.
 */
export function loadConfig(configPath: string): MinerConfig {
  if (!existsSync(configPath)) {
    return { ...DEFAULT_CONFIG };
  }

  let raw: Record<string, unknown>;
  try {
    const content = readFileSync(configPath, "utf-8");
    raw = (YAML.parse(content) as Record<string, unknown>) ?? {};
  } catch {
    return { ...DEFAULT_CONFIG };
  }

  const rawSources = (raw.sources ?? {}) as Record<string, unknown>;
  const rawShip = (raw.ship ?? {}) as Record<string, unknown>;
  const rawPrivacy = (raw.privacy ?? {}) as Record<string, unknown>;

  return {
    sources: {
      claude_code: rawSources.claude_code !== undefined
        ? Boolean(rawSources.claude_code)
        : DEFAULT_CONFIG.sources.claude_code,
      codex: rawSources.codex !== undefined
        ? Boolean(rawSources.codex)
        : DEFAULT_CONFIG.sources.codex,
      cursor: rawSources.cursor !== undefined
        ? Boolean(rawSources.cursor)
        : DEFAULT_CONFIG.sources.cursor,
    },
    ship: {
      endpoint: (rawShip.endpoint as string) ?? DEFAULT_CONFIG.ship.endpoint,
      redactSecrets: rawShip.redactSecrets !== undefined
        ? Boolean(rawShip.redactSecrets)
        : DEFAULT_CONFIG.ship.redactSecrets,
      schedule: (rawShip.schedule as MinerConfig["ship"]["schedule"]) ??
        DEFAULT_CONFIG.ship.schedule,
      disclosure: (rawShip.disclosure as DisclosureLevel) ??
        DEFAULT_CONFIG.ship.disclosure,
      anonymize: rawShip.anonymize !== undefined
        ? Boolean(rawShip.anonymize)
        : DEFAULT_CONFIG.ship.anonymize,
    },
    privacy: {
      excludeProjects: Array.isArray(rawPrivacy.excludeProjects)
        ? rawPrivacy.excludeProjects
        : DEFAULT_CONFIG.privacy.excludeProjects,
    },
    pollIntervalMs: typeof raw.pollIntervalMs === "number"
      ? raw.pollIntervalMs
      : DEFAULT_CONFIG.pollIntervalMs,
    developer: (raw.developer as string) ?? DEFAULT_CONFIG.developer,
    machine: (raw.machine as string) ?? DEFAULT_CONFIG.machine,
  };
}
