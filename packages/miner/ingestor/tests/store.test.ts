import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Store, type StoredBatch } from "../src/store";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-store-"));
}

describe("Store", () => {
  let dataDir: string;
  let store: Store;

  beforeEach(() => {
    dataDir = makeTmpDir();
    store = new Store(dataDir);
  });

  const makeBatch = (overrides?: Partial<StoredBatch>): StoredBatch => ({
    developer: "alice@acme.com",
    machine: "alice-mac",
    agent: "claude_code",
    project: "test-proj",
    sourceFile: "/tmp/session.jsonl",
    shippedAt: "2026-04-08T17:00:00Z",
    receivedAt: "2026-04-08T17:00:01Z",
    entries: ['{"type":"user","text":"hello"}', '{"type":"assistant","text":"hi"}'],
    ...overrides,
  });

  it("stores a batch as a JSONL file in the raw zone", () => {
    store.saveBatch(makeBatch());
    const rawDir = join(dataDir, "raw", "claude_code");
    expect(existsSync(rawDir)).toBe(true);
    const files = readdirSync(rawDir);
    const jsonlFiles = files.filter((f) => f.endsWith(".jsonl"));
    expect(jsonlFiles).toHaveLength(1);
    expect(jsonlFiles[0]).toMatch(/\.jsonl$/);
  });

  it("stores entries as individual JSONL lines", () => {
    store.saveBatch(makeBatch({ entries: ['{"a":1}', '{"a":2}', '{"a":3}'] }));
    const rawDir = join(dataDir, "raw", "claude_code");
    const file = readdirSync(rawDir)[0];
    const content = readFileSync(join(rawDir, file), "utf-8");
    const lines = content.trim().split("\n");
    expect(lines).toHaveLength(3);
  });

  it("includes metadata in filename", () => {
    store.saveBatch(makeBatch({ developer: "bob", agent: "codex" }));
    const rawDir = join(dataDir, "raw", "codex");
    const file = readdirSync(rawDir)[0];
    expect(file).toContain("bob");
    expect(file).toContain("codex");
  });

  it("organizes by agent type", () => {
    store.saveBatch(makeBatch({ agent: "claude_code" }));
    store.saveBatch(makeBatch({ agent: "codex" }));
    store.saveBatch(makeBatch({ agent: "cursor" }));

    expect(existsSync(join(dataDir, "raw", "claude_code"))).toBe(true);
    expect(existsSync(join(dataDir, "raw", "codex"))).toBe(true);
    expect(existsSync(join(dataDir, "raw", "cursor"))).toBe(true);
  });

  it("saves batch metadata alongside entries", () => {
    store.saveBatch(makeBatch());
    const rawDir = join(dataDir, "raw", "claude_code");
    const files = readdirSync(rawDir);
    const metaFile = files.find((f) => f.endsWith(".meta.json"));
    expect(metaFile).toBeDefined();

    const meta = JSON.parse(readFileSync(join(rawDir, metaFile!), "utf-8"));
    expect(meta.developer).toBe("alice@acme.com");
    expect(meta.machine).toBe("alice-mac");
    expect(meta.entryCount).toBe(2);
  });

  it("returns batch stats", () => {
    const stats = store.saveBatch(makeBatch({ entries: ['{"x":1}', '{"x":2}'] }));
    expect(stats.entryCount).toBe(2);
    expect(stats.filePath).toBeTruthy();
  });

  it("listBatches returns stored batch metadata", () => {
    store.saveBatch(makeBatch({ agent: "claude_code", developer: "alice" }));
    store.saveBatch(makeBatch({ agent: "codex", developer: "bob" }));

    const batches = store.listBatches();
    expect(batches).toHaveLength(2);
  });
});
