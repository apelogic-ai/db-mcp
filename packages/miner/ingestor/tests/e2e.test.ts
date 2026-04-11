/**
 * E2E test: miner agent → ingestor server → stored in lakehouse.
 *
 * Spins up a real ingestor server, creates fake trace data,
 * runs the agent shipper against it, verifies data landed.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

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
import type { Server } from "node:http";

// Agent modules
import { Shipper } from "../../agent/src/shipper";
import { createHttpShipper } from "../../agent/src/http-shipper";
import { generateKeypair, loadKeypair, getPublicKeyFingerprint } from "../../agent/src/identity";

// Ingestor modules
import { createIngestor } from "../src/server";

const PORT = 19878;

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-e2e-"));
}

describe("E2E: agent → ingestor → lakehouse", () => {
  let server: Server;
  let lakehouseDir: string;
  let agentStateDir: string;
  let keyDir: string;

  beforeAll(async () => {
    lakehouseDir = makeTmpDir();
    agentStateDir = makeTmpDir();
    keyDir = makeTmpDir();

    // Generate agent keypair
    generateKeypair(keyDir);
    const kp = loadKeypair(keyDir)!;
    const fp = getPublicKeyFingerprint(kp.publicKeyPem);

    // Start ingestor with the agent's public key registered
    server = await createIngestor({
      port: PORT,
      dataDir: lakehouseDir,
      trustedKeys: { [fp]: kp.publicKeyPem },
      apiKeys: ["key_e2e_test"],
    });
  });

  afterAll(() => {
    server?.close();
  });

  it("agent ships trace data to ingestor via API key", async () => {
    // Create fake trace file
    const traceDir = makeTmpDir();
    const projectDir = join(traceDir, "projects", "e2e-proj");
    mkdirSync(projectDir, { recursive: true });
    const traceFile = join(projectDir, "session.jsonl");
    writeFileSync(
      traceFile,
      [
        JSON.stringify({ type: "user", timestamp: "2026-04-08T20:00:00Z", message: { content: [{ type: "text", text: "E2E test message" }] } }),
        JSON.stringify({ type: "assistant", timestamp: "2026-04-08T20:00:01Z", message: { content: [{ type: "tool_use", name: "Bash", input: { command: "echo hello" } }], usage: { input_tokens: 100, output_tokens: 50 } } }),
      ].join("\n") + "\n",
    );

    // Create shipper with HTTP backend
    const httpShip = createHttpShipper({
      endpoint: `http://localhost:${PORT}/api/ingest`,
      apiKey: "key_e2e_test",
    });

    const shipper = new Shipper({
      developer: "e2e-developer@acme.com",
      machine: "e2e-machine",
      stateDir: agentStateDir,
      redactSecrets: true,
      ship: httpShip,
    });

    // Process the trace file
    shipper.processFile(traceFile, "claude_code", "e2e-proj");

    // Wait for async ship to complete
    await new Promise((r) => setTimeout(r, 100));

    // Verify data landed in the lakehouse
    const jsonlFiles = findFiles(join(lakehouseDir, "raw"), ".jsonl");
    expect(jsonlFiles.length).toBeGreaterThanOrEqual(1);

    const content = readFileSync(jsonlFiles[0], "utf-8");
    expect(content).toContain("E2E test message");
    expect(content).toContain("echo hello");
    expect(jsonlFiles[0]).toContain("agent=claude_code");

    // Verify metadata
    const metaFiles = findFiles(join(lakehouseDir, "raw"), ".meta.json");
    const meta = JSON.parse(readFileSync(metaFiles[0], "utf-8"));
    expect(meta.developer).toBe("e2e-developer@acme.com");
    expect(meta.machine).toBe("e2e-machine");
    expect(meta.agent).toBe("claude_code");
    expect(meta.entryCount).toBe(2);
  });

  it("agent ships signed data to ingestor via Ed25519", async () => {
    const kp = loadKeypair(keyDir)!;

    const traceDir = makeTmpDir();
    const projectDir = join(traceDir, "projects", "signed-proj");
    mkdirSync(projectDir, { recursive: true });
    const traceFile = join(projectDir, "signed.jsonl");
    writeFileSync(
      traceFile,
      JSON.stringify({ type: "user", timestamp: "2026-04-08T21:00:00Z", message: { content: [{ type: "text", text: "Signed E2E" }] } }) + "\n",
    );

    const signedStateDir = makeTmpDir();

    const httpShip = createHttpShipper({
      endpoint: `http://localhost:${PORT}/api/ingest`,
      keypair: kp,
    });

    const shipper = new Shipper({
      developer: "signer@acme.com",
      machine: "sign-machine",
      stateDir: signedStateDir,
      redactSecrets: false,
      ship: httpShip,
    });

    shipper.processFile(traceFile, "codex", "signed-proj");
    await new Promise((r) => setTimeout(r, 100));

    // Verify in lakehouse
    const metaFiles = findFiles(join(lakehouseDir, "raw"), ".meta.json").filter((f) => f.includes("agent=codex"));
    expect(metaFiles.length).toBeGreaterThanOrEqual(1);

    const meta = JSON.parse(readFileSync(metaFiles[0], "utf-8"));
    expect(meta.developer).toBe("signer@acme.com");
  });

  it("secret redaction works end-to-end", async () => {
    const traceDir = makeTmpDir();
    const projectDir = join(traceDir, "projects", "secrets-proj");
    mkdirSync(projectDir, { recursive: true });
    const traceFile = join(projectDir, "secrets.jsonl");
    writeFileSync(
      traceFile,
      JSON.stringify({ type: "user", timestamp: "2026-04-08T22:00:00Z", message: { content: [{ type: "text", text: "key: AKIAIOSFODNN7EXAMPLE" }] } }) + "\n",
    );

    const secretsStateDir = makeTmpDir();
    const httpShip = createHttpShipper({
      endpoint: `http://localhost:${PORT}/api/ingest`,
      apiKey: "key_e2e_test",
    });

    const shipper = new Shipper({
      developer: "secrets-dev",
      stateDir: secretsStateDir,
      redactSecrets: true,
      ship: httpShip,
    });

    shipper.processFile(traceFile, "claude_code", "secrets-proj");
    await new Promise((r) => setTimeout(r, 100));

    // Verify the secret was redacted in the lakehouse
    const jsonlFiles = findFiles(join(lakehouseDir, "raw"), ".jsonl");
    const allContent = jsonlFiles.map((f) => readFileSync(f, "utf-8")).join("\n");

    expect(allContent).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(allContent).toContain("[REDACTED:aws_access_key]");
  });
});
