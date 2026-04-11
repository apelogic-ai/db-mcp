import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync, readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  generateConfig,
  writeConfig,
  type InitAnswers,
} from "../src/init";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-init-"));
}

describe("generateConfig", () => {
  it("generates config from init answers", () => {
    const answers: InitAnswers = {
      developer: "alice@acme.com",
      agents: { claude_code: true, codex: true, cursor: false },
      includeOrgs: ["acme-corp", "acme-data"],
      endpoint: "https://miner.acme.com/api/ingest",
      apiKey: "key_prod_123",
      enableDaemon: true,
    };

    const config = generateConfig(answers);
    expect(config).toContain("alice@acme.com");
    expect(config).toContain("claude_code: true");
    expect(config).toContain("codex: true");
    expect(config).toContain("cursor: false");
    expect(config).toContain("acme-corp");
    expect(config).toContain("acme-data");
    expect(config).toContain("https://miner.acme.com/api/ingest");
  });

  it("handles local-only mode (no endpoint)", () => {
    const answers: InitAnswers = {
      developer: "bob@example.com",
      agents: { claude_code: true, codex: false, cursor: false },
      includeOrgs: [],
      endpoint: null,
      apiKey: null,
      enableDaemon: false,
    };

    const config = generateConfig(answers);
    expect(config).toContain("endpoint: null");
    expect(config).toContain("enabled: false"); // ship.enabled
  });

  it("generates valid YAML", () => {
    const answers: InitAnswers = {
      developer: "carol@test.com",
      agents: { claude_code: true, codex: true, cursor: true },
      includeOrgs: ["my-org"],
      endpoint: "http://localhost:19900/api/ingest",
      apiKey: null,
      enableDaemon: true,
    };

    const config = generateConfig(answers);
    // Should be parseable YAML
    const YAML = require("yaml");
    const parsed = YAML.parse(config);
    expect(parsed.developer).toBe("carol@test.com");
    expect(parsed.sources.claude_code).toBe(true);
    expect(parsed.scope.include_orgs).toEqual(["my-org"]);
  });
});

describe("writeConfig", () => {
  it("writes config to ~/.miner/config.yaml", () => {
    const stateDir = makeTmpDir();
    const configContent = "developer: test@example.com\n";

    writeConfig(stateDir, configContent);

    const configPath = join(stateDir, "config.yaml");
    expect(existsSync(configPath)).toBe(true);
    expect(readFileSync(configPath, "utf-8")).toBe(configContent);
  });

  it("creates the directory if needed", () => {
    const baseDir = makeTmpDir();
    const stateDir = join(baseDir, "nested", ".miner");

    writeConfig(stateDir, "test: true\n");

    expect(existsSync(join(stateDir, "config.yaml"))).toBe(true);
  });

  it("does NOT overwrite existing config without force", () => {
    const stateDir = makeTmpDir();
    writeConfig(stateDir, "original: true\n");
    writeConfig(stateDir, "overwrite: true\n"); // should not overwrite

    const content = readFileSync(join(stateDir, "config.yaml"), "utf-8");
    expect(content).toContain("original");
  });

  it("overwrites with force flag", () => {
    const stateDir = makeTmpDir();
    writeConfig(stateDir, "original: true\n");
    writeConfig(stateDir, "overwrite: true\n", true);

    const content = readFileSync(join(stateDir, "config.yaml"), "utf-8");
    expect(content).toContain("overwrite");
  });
});
