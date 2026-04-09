import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import { mkdtempSync, readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

/** Recursively find files matching a suffix. */
function findFiles(dir: string, suffix: string): string[] {
  const results: string[] = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) results.push(...findFiles(full, suffix));
    else if (entry.name.endsWith(suffix)) results.push(full);
  }
  return results;
}
import { createIngestor, type IngestorConfig } from "../src/server";
import type { Server } from "node:http";

// Reuse identity module from the agent package for signing in tests
import { generateKeypair, loadKeypair, signPayload, getPublicKeyFingerprint } from "../../agent/src/identity";

const PORT = 19877;

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-ingestor-"));
}

describe("Ingestor server", () => {
  let dataDir: string;
  let server: Server;
  let keyDir: string;

  beforeAll(async () => {
    dataDir = makeTmpDir();
    keyDir = makeTmpDir();
    generateKeypair(keyDir);

    const kp = loadKeypair(keyDir)!;
    const fp = getPublicKeyFingerprint(kp.publicKeyPem);

    const config: IngestorConfig = {
      port: PORT,
      dataDir,
      // Register the test key
      trustedKeys: { [fp]: kp.publicKeyPem },
      apiKeys: ["key_test_valid"],
    };
    server = await createIngestor(config);
  });

  afterAll(() => {
    server?.close();
  });

  const baseUrl = `http://localhost:${PORT}`;

  async function post(
    path: string,
    body: unknown,
    headers?: Record<string, string>,
  ): Promise<{ status: number; body: unknown }> {
    const res = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let parsed: unknown;
    try { parsed = JSON.parse(text); } catch { parsed = text; }
    return { status: res.status, body: parsed };
  }

  it("accepts a valid batch with API key auth", async () => {
    const batch = {
      developer: "alice@acme.com",
      machine: "alice-mac",
      agent: "claude_code",
      project: "test-proj",
      sourceFile: "/tmp/session.jsonl",
      shippedAt: "2026-04-08T17:00:00Z",
      entries: ['{"type":"user"}'],
    };

    const res = await post("/api/ingest", batch, {
      Authorization: "Bearer key_test_valid",
    });
    expect(res.status).toBe(200);
    expect((res.body as Record<string, unknown>).status).toBe("ok");
  });

  it("rejects request without auth", async () => {
    const res = await post("/api/ingest", {
      developer: "x",
      machine: "m",
      agent: "claude_code",
      project: "p",
      sourceFile: "f",
      shippedAt: "2026-04-08T17:00:00Z",
      entries: ["{}"],
    });
    expect(res.status).toBe(401);
  });

  it("rejects invalid API key", async () => {
    const res = await post(
      "/api/ingest",
      { developer: "x", machine: "m", agent: "a", project: "p", sourceFile: "f", shippedAt: "t", entries: ["{}"] },
      { Authorization: "Bearer key_wrong" },
    );
    expect(res.status).toBe(401);
  });

  it("accepts batch with valid Ed25519 signature", async () => {
    const kp = loadKeypair(keyDir)!;
    const batch = {
      developer: "bob",
      machine: "bob-pc",
      agent: "codex",
      project: "signed-proj",
      sourceFile: "/tmp/f.jsonl",
      shippedAt: "2026-04-08T18:00:00Z",
      entries: ['{"signed":true}'],
    };
    const body = JSON.stringify(batch);
    const sig = signPayload(body, kp);
    const fp = getPublicKeyFingerprint(kp.publicKeyPem);

    const res = await fetch(`${baseUrl}/api/ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Miner-Signature": sig,
        "X-Miner-Key-Fingerprint": fp,
      },
      body,
    });
    expect(res.status).toBe(200);
  });

  it("rejects tampered batch with valid signature", async () => {
    const kp = loadKeypair(keyDir)!;
    const batch = { developer: "carol", machine: "m", agent: "claude_code", project: "p", sourceFile: "f", shippedAt: "t", entries: ["{}"] };
    const body = JSON.stringify(batch);
    const sig = signPayload(body, kp);
    const fp = getPublicKeyFingerprint(kp.publicKeyPem);

    // Tamper with the body
    const tampered = JSON.stringify({ ...batch, developer: "mallory" });

    const res = await fetch(`${baseUrl}/api/ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Miner-Signature": sig,
        "X-Miner-Key-Fingerprint": fp,
      },
      body: tampered,
    });
    expect(res.status).toBe(403);
  });

  it("rejects unknown key fingerprint", async () => {
    const unknownKeyDir = makeTmpDir();
    generateKeypair(unknownKeyDir);
    const unknownKp = loadKeypair(unknownKeyDir)!;

    const batch = { developer: "eve", machine: "m", agent: "codex", project: "p", sourceFile: "f", shippedAt: "t", entries: ["{}"] };
    const body = JSON.stringify(batch);
    const sig = signPayload(body, unknownKp);
    const fp = getPublicKeyFingerprint(unknownKp.publicKeyPem);

    const res = await fetch(`${baseUrl}/api/ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Miner-Signature": sig,
        "X-Miner-Key-Fingerprint": fp,
      },
      body,
    });
    expect(res.status).toBe(401);
  });

  it("stores the batch in the lakehouse", async () => {
    const batch = {
      developer: "stored@acme.com",
      machine: "m",
      agent: "claude_code",
      project: "store-test",
      sourceFile: "/tmp/s.jsonl",
      shippedAt: "2026-04-08T19:00:00Z",
      entries: ['{"stored":true}', '{"stored":2}'],
    };

    await post("/api/ingest", batch, { Authorization: "Bearer key_test_valid" });

    const jsonlFiles = findFiles(join(dataDir, "raw"), ".jsonl");
    expect(jsonlFiles.length).toBeGreaterThanOrEqual(1);

    // Find the file containing our test data
    const storedFile = jsonlFiles.find((f) =>
      readFileSync(f, "utf-8").includes('"stored":true')
    );
    expect(storedFile).toBeDefined();
    expect(storedFile!).toContain("agent=claude_code");
  });

  it("returns health check on GET /health", async () => {
    const res = await fetch(`${baseUrl}/health`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
  });
});
