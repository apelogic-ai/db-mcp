import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
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
      developer: "test-user@example.com",
      machine: "test-machine",
      stateDir,
      ship: async (batch) => {
        shipped.push(batch);
      },
    };
  });

  it("tracks cursor per file — only ships new lines", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n{"line":2}\n');

    const shipper = new Shipper(config);
    await shipper.processFile(traceFile, "claude_code", "test-project");

    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries).toHaveLength(2);

    // Append more lines
    writeFileSync(traceFile, '{"line":1}\n{"line":2}\n{"line":3}\n');
    shipped = [];

    await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries).toHaveLength(1);
    expect(shipped[0].entries[0]).toContain('"line":3');
  });

  it("persists cursor across instances", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n{"line":2}\n');

    const shipper1 = new Shipper(config);
    await shipper1.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(1);

    shipped = [];
    const shipper2 = new Shipper(config);
    await shipper2.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(0);
  });

  it("redacts secrets before shipping", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"content":"key: AKIAIOSFODNN7EXAMPLE"}\n');

    const shipper = new Shipper({ ...config, redactSecrets: true });
    await shipper.processFile(traceFile, "claude_code", "test-project");

    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries[0]).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(shipped[0].entries[0]).toContain("[REDACTED:aws_access_key]");
  });

  it("includes developer, machine, and batchId", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n');

    const shipper = new Shipper(config);
    await shipper.processFile(traceFile, "claude_code", "test-project");

    expect(shipped[0].developer).toBe("test-user@example.com");
    expect(shipped[0].machine).toBe("test-machine");
    expect(shipped[0].batchId).toBeTruthy();
    expect(shipped[0].batchId.length).toBe(16);
  });

  it("does NOT advance cursor when ship fails", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n');

    let failCount = 0;
    const failingConfig: ShipperConfig = {
      ...config,
      ship: async () => {
        failCount++;
        throw new Error("Network error");
      },
    };

    const shipper = new Shipper(failingConfig);
    const result = await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(result).toBe(false);
    expect(failCount).toBe(1);

    // Retry — should attempt again (cursor was NOT advanced)
    const result2 = await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(result2).toBe(false);
    expect(failCount).toBe(2);
  });

  it("advances cursor when ship succeeds after previous failure", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n');

    let callCount = 0;
    const retryConfig: ShipperConfig = {
      ...config,
      ship: async (batch) => {
        callCount++;
        if (callCount === 1) throw new Error("First call fails");
        shipped.push(batch);
      },
    };

    const shipper = new Shipper(retryConfig);

    // First attempt fails
    await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(0);

    // Second attempt succeeds
    await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(1);

    // Third attempt — nothing new (cursor advanced)
    shipped = [];
    await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(0);
  });

  it("generates deterministic batchId for same content", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "session.jsonl");
    writeFileSync(traceFile, '{"line":1}\n');

    let callCount = 0;
    const ids: string[] = [];
    const captureConfig: ShipperConfig = {
      ...config,
      ship: async (batch) => {
        callCount++;
        ids.push(batch.batchId);
        if (callCount === 1) throw new Error("Fail first");
      },
    };

    const shipper = new Shipper(captureConfig);
    await shipper.processFile(traceFile, "claude_code", "test-project");
    await shipper.processFile(traceFile, "claude_code", "test-project");

    // Same content → same batchId on retry
    expect(ids).toHaveLength(2);
    expect(ids[0]).toBe(ids[1]);
  });

  it("resolves developer from git config when not set", () => {
    const shipper = new Shipper({ stateDir, ship: async () => {} });
    expect(shipper.developer).toBeTruthy();
    expect(shipper.developer).not.toBe("unknown");
  });

  it("resolves machine from hostname when not set", () => {
    const shipper = new Shipper({ stateDir, ship: async () => {} });
    expect(shipper.machine).toBeTruthy();
  });

  it("handles empty files", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "empty.jsonl");
    writeFileSync(traceFile, "");

    const shipper = new Shipper(config);
    await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(0);
  });

  it("skips invalid JSON lines", async () => {
    const traceDir = makeTmpDir();
    const traceFile = join(traceDir, "messy.jsonl");
    writeFileSync(traceFile, '{"good":1}\nnot json\n{"good":2}\n');

    const shipper = new Shipper(config);
    await shipper.processFile(traceFile, "claude_code", "test-project");
    expect(shipped).toHaveLength(1);
    expect(shipped[0].entries).toHaveLength(2);
  });
});
