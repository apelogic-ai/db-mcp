import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { loadConfig, type MinerConfig, DEFAULT_CONFIG } from "../src/config";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-config-"));
}

describe("loadConfig", () => {
  it("returns defaults when no config file exists", () => {
    const config = loadConfig("/nonexistent/config.yaml");
    expect(config.sources.claude_code).toBe(true);
    expect(config.sources.codex).toBe(true);
    expect(config.sources.cursor).toBe(true);
    expect(config.ship.redactSecrets).toBe(true);
  });

  it("loads from YAML file", () => {
    const dir = makeTmpDir();
    const configFile = join(dir, "config.yaml");
    writeFileSync(configFile, `
sources:
  claude_code: true
  codex: false
  cursor: true
ship:
  endpoint: https://miner.acme.com/api/ingest
  redactSecrets: true
developer: alice@acme.com
`);
    const config = loadConfig(configFile);
    expect(config.sources.codex).toBe(false);
    expect(config.ship.endpoint).toBe("https://miner.acme.com/api/ingest");
    expect(config.developer).toBe("alice@acme.com");
  });

  it("merges partial config with defaults", () => {
    const dir = makeTmpDir();
    const configFile = join(dir, "config.yaml");
    writeFileSync(configFile, `
sources:
  cursor: false
`);
    const config = loadConfig(configFile);
    expect(config.sources.cursor).toBe(false);
    // Others keep defaults
    expect(config.sources.claude_code).toBe(true);
    expect(config.sources.codex).toBe(true);
    expect(config.ship.redactSecrets).toBe(true);
  });

  it("respects poll interval", () => {
    const dir = makeTmpDir();
    const configFile = join(dir, "config.yaml");
    writeFileSync(configFile, `
pollIntervalMs: 30000
`);
    const config = loadConfig(configFile);
    expect(config.pollIntervalMs).toBe(30000);
  });

  it("handles exclude_projects", () => {
    const dir = makeTmpDir();
    const configFile = join(dir, "config.yaml");
    writeFileSync(configFile, `
privacy:
  excludeProjects:
    - client-nda-project
    - secret-repo
`);
    const config = loadConfig(configFile);
    expect(config.privacy.excludeProjects).toEqual([
      "client-nda-project",
      "secret-repo",
    ]);
  });

  it("DEFAULT_CONFIG has sane values", () => {
    expect(DEFAULT_CONFIG.pollIntervalMs).toBeGreaterThan(0);
    expect(DEFAULT_CONFIG.sources.claude_code).toBe(true);
    expect(DEFAULT_CONFIG.ship.redactSecrets).toBe(true);
    expect(DEFAULT_CONFIG.privacy.excludeProjects).toEqual([]);
  });
});
