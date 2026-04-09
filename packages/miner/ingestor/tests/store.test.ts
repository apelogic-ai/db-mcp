import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Store, type StoredBatch } from "../src/store";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-store-"));
}

/** Recursively find all files matching a pattern. */
function findFiles(dir: string, suffix: string): string[] {
  const results: string[] = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findFiles(full, suffix));
    } else if (entry.name.endsWith(suffix)) {
      results.push(full);
    }
  }
  return results;
}

describe("Store", () => {
  let dataDir: string;
  let store: Store;

  beforeEach(() => {
    dataDir = makeTmpDir();
    store = new Store(dataDir);
  });

  const makeBatch = (overrides?: Partial<StoredBatch>): StoredBatch => ({
    batchId: "test_batch_001",
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

  it("stores a batch in Hive-partitioned directory", () => {
    store.saveBatch(makeBatch());
    const jsonlFiles = findFiles(dataDir, ".jsonl");
    expect(jsonlFiles).toHaveLength(1);
    // Verify Hive partitioning path
    expect(jsonlFiles[0]).toContain("year=2026");
    expect(jsonlFiles[0]).toContain("month=04");
    expect(jsonlFiles[0]).toContain("day=08");
    expect(jsonlFiles[0]).toContain("agent=claude_code");
  });

  it("uses batchId as filename", () => {
    store.saveBatch(makeBatch({ batchId: "abc123def456" }));
    const jsonlFiles = findFiles(dataDir, ".jsonl");
    expect(jsonlFiles[0]).toContain("abc123def456.jsonl");
  });

  it("stores entries as individual JSONL lines", () => {
    store.saveBatch(makeBatch({ entries: ['{"a":1}', '{"a":2}', '{"a":3}'] }));
    const jsonlFiles = findFiles(dataDir, ".jsonl");
    const content = readFileSync(jsonlFiles[0], "utf-8");
    const lines = content.trim().split("\n");
    expect(lines).toHaveLength(3);
  });

  it("partitions by agent type", () => {
    store.saveBatch(makeBatch({ batchId: "b1", agent: "claude_code" }));
    store.saveBatch(makeBatch({ batchId: "b2", agent: "codex" }));
    store.saveBatch(makeBatch({ batchId: "b3", agent: "cursor" }));

    const all = findFiles(dataDir, ".jsonl");
    expect(all).toHaveLength(3);
    expect(all.some((f) => f.includes("agent=claude_code"))).toBe(true);
    expect(all.some((f) => f.includes("agent=codex"))).toBe(true);
    expect(all.some((f) => f.includes("agent=cursor"))).toBe(true);
  });

  it("saves batch metadata alongside entries", () => {
    store.saveBatch(makeBatch());
    const metaFiles = findFiles(dataDir, ".meta.json");
    expect(metaFiles).toHaveLength(1);

    const meta = JSON.parse(readFileSync(metaFiles[0], "utf-8"));
    expect(meta.developer).toBe("alice@acme.com");
    expect(meta.machine).toBe("alice-mac");
    expect(meta.entryCount).toBe(2);
    expect(meta.batchId).toBe("test_batch_001");
  });

  it("returns batch stats", () => {
    const stats = store.saveBatch(makeBatch({ entries: ['{"x":1}', '{"x":2}'] }));
    expect(stats.entryCount).toBe(2);
    expect(stats.filePath).toBeTruthy();
    expect(stats.filePath).toContain(".jsonl");
  });

  it("deduplicates by batchId", () => {
    store.saveBatch(makeBatch({ batchId: "dedup_test" }));
    const result = store.saveBatch(makeBatch({ batchId: "dedup_test" }));
    expect(result.duplicate).toBe(true);
    expect(result.entryCount).toBe(0);

    // Only one file written
    const jsonlFiles = findFiles(dataDir, ".jsonl");
    expect(jsonlFiles).toHaveLength(1);
  });

  it("dedup persists across store instances", () => {
    store.saveBatch(makeBatch({ batchId: "persist_test" }));

    const store2 = new Store(dataDir);
    expect(store2.isDuplicate("persist_test")).toBe(true);
  });

  it("dedup log is append-only", () => {
    store.saveBatch(makeBatch({ batchId: "id_1" }));
    store.saveBatch(makeBatch({ batchId: "id_2" }));
    store.saveBatch(makeBatch({ batchId: "id_3" }));

    const logContent = readFileSync(join(dataDir, "dedup.log"), "utf-8");
    const lines = logContent.trim().split("\n");
    expect(lines).toEqual(["id_1", "id_2", "id_3"]);
  });

  it("listBatches walks partitioned directories", () => {
    store.saveBatch(makeBatch({ batchId: "b1", agent: "claude_code" }));
    store.saveBatch(makeBatch({ batchId: "b2", agent: "codex", shippedAt: "2026-04-09T10:00:00Z" }));

    const batches = store.listBatches();
    expect(batches).toHaveLength(2);
  });

  it("generates batchId when not provided", () => {
    store.saveBatch(makeBatch({ batchId: undefined }));
    const jsonlFiles = findFiles(dataDir, ".jsonl");
    expect(jsonlFiles).toHaveLength(1);
    // Filename should be a hex hash, not "undefined"
    expect(jsonlFiles[0]).not.toContain("undefined");
  });

  it("files are immutable — same batchId never overwrites", () => {
    store.saveBatch(makeBatch({ batchId: "immutable_test", entries: ['{"v":1}'] }));

    // Attempt to save different content with same batchId
    const result = store.saveBatch(makeBatch({ batchId: "immutable_test", entries: ['{"v":2}'] }));
    expect(result.duplicate).toBe(true);

    // Original content preserved
    const jsonlFiles = findFiles(dataDir, ".jsonl");
    const content = readFileSync(jsonlFiles[0], "utf-8");
    expect(content).toContain('"v":1');
    expect(content).not.toContain('"v":2');
  });
});
