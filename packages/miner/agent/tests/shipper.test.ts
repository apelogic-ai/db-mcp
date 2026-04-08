import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Shipper, type ShipperConfig, type ShippedBatch } from "../src/shipper";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-shipper-"));
}

describe("Shipper", () => {
  let stateDir: string;
  let config: ShipperConfig;
  let shipped: ShippedBatch[];

  beforeEach(() => {
    stateDir = makeTmpDir();
    shipped = [];
    config = {
      developer: "test-user",
      machine: "test-machine",
      stateDir,
      ship: async (batch) => {
        shipped.push(batch);
      },
    };
  });

  it("tracks cursor per file — only ships new lines", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n{"line":2}\n');

    const shipper = new Shipper(config);
    shipper.processFile(traceFile, "claude_code", "test-project");

    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries).toHaveLength(2);

    // Append more lines
    writeFileSync(traceFile, '{"line":1}\n{"line":2}\n{"line":3}\n');
    shipped = [];

    shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries).toHaveLength(1); // only line 3
    expect(shipped[0].entries[0]).toContain('"line":3');
  });

  it("persists cursor across instances", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n{"line":2}\n');

    const shipper1 = new Shipper(config);
    shipper1.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(1);

    // New instance reads persisted cursor
    shipped = [];
    const shipper2 = new Shipper(config);
    shipper2.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(0); // nothing new
  });

  it("redacts secrets before shipping", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(
      traceFile,
      '{"content":"key: AKIAIOSFODNN7EXAMPLE"}\n'
    );

    const shipper = new Shipper({ ...config, redactSecrets: true } as ShipperConfig);
    shipper.processFile(traceFile, "claude_code", "test-project");

    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries[0]).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(shipped[0].entries[0]).toContain("[REDACTED:aws_access_key]");
  });

  it("includes developer and machine attribution", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n');

    const shipper = new Shipper(config);
    shipper.processFile(traceFile, "claude_code", "test-project");

    expect(shipped[0].developer).toBe("test-user");
    expect(shipped[0].machine).toBe("test-machine");
    expect(shipped[0].shippedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("includes metadata in batch", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n');

    const shipper = new Shipper(config);
    shipper.processFile(traceFile, "codex", "my-project");

    expect(shipped[0].agent).toBe("codex");
    expect(shipped[0].project).toBe("my-project");
    expect(shipped[0].sourceFile).toBe(traceFile);
  });

  it("handles empty files gracefully", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "empty.jsonl");
    writeFileSync(traceFile, "");

    const shipper = new Shipper(config);
    shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(0);
  });

  it("skips invalid JSON lines without crashing", () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "messy.jsonl");
    writeFileSync(
      traceFile,
      '{"good":1}\nnot json\n{"good":2}\n'
    );

    const shipper = new Shipper(config);
    shipper.processFile(traceFile, "claude_code", "test-project");

    // Ships valid lines, skips invalid
    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries).toHaveLength(2);
  });
});
