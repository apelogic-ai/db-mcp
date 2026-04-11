/**
 * Ingestor HTTP server — receives trace batches from miner agents.
 *
 * Authentication (either is sufficient):
 * - Bearer API key (Authorization header)
 * - Ed25519 signature (X-Miner-Signature + X-Miner-Key-Fingerprint headers)
 *
 * On valid auth: stores batch to the lakehouse (Store).
 */

import { createServer, type Server, type IncomingMessage, type ServerResponse } from "node:http";
import { createVerify, createPublicKey, verify as cryptoVerify } from "node:crypto";
import { Store } from "./store";

export interface IngestorConfig {
  port: number;
  dataDir: string;
  trustedKeys?: Record<string, string>;   // fingerprint → PEM public key
  apiKeys?: string[];                      // valid API keys
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

function json(res: ServerResponse, status: number, data: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(data));
}

function verifyEd25519(payload: string, signature: string, publicKeyPem: string): boolean {
  try {
    const publicKey = createPublicKey(publicKeyPem);
    return cryptoVerify(null, Buffer.from(payload), publicKey, Buffer.from(signature, "base64"));
  } catch {
    return false;
  }
}

export function createIngestor(config: IngestorConfig): Promise<Server> {
  const store = new Store(config.dataDir);
  const validApiKeys = new Set(config.apiKeys ?? []);
  const trustedKeys = config.trustedKeys ?? {};

  const server = createServer(async (req, res) => {
    // Health check
    if (req.method === "GET" && req.url === "/health") {
      json(res, 200, { status: "ok" });
      return;
    }

    // Ingest endpoint
    if (req.method === "POST" && req.url === "/api/ingest") {
      const body = await readBody(req);

      // --- Authentication ---
      const authHeader = req.headers["authorization"];
      const signature = req.headers["x-miner-signature"] as string | undefined;
      const fingerprint = req.headers["x-miner-key-fingerprint"] as string | undefined;

      let authenticated = false;

      // API key auth
      if (authHeader?.startsWith("Bearer ")) {
        const key = authHeader.slice(7);
        if (validApiKeys.has(key)) {
          authenticated = true;
        }
      }

      // Signature auth
      if (!authenticated && signature && fingerprint) {
        const publicKeyPem = trustedKeys[fingerprint];
        if (!publicKeyPem) {
          json(res, 401, { error: "Unknown key fingerprint" });
          return;
        }
        if (!verifyEd25519(body, signature, publicKeyPem)) {
          json(res, 403, { error: "Invalid signature" });
          return;
        }
        authenticated = true;
      }

      if (!authenticated) {
        json(res, 401, { error: "Authentication required" });
        return;
      }

      // --- Parse and store ---
      let batch: Record<string, unknown>;
      try {
        batch = JSON.parse(body);
      } catch {
        json(res, 400, { error: "Invalid JSON" });
        return;
      }

      const entries = batch.entries;
      if (!Array.isArray(entries)) {
        json(res, 400, { error: "Missing entries array" });
        return;
      }

      const batchId = typeof batch.batchId === "string" ? batch.batchId : undefined;
      const developer = String(batch.developer ?? "unknown");

      // Dedup: if we've already received this batchId, return 200 (idempotent)
      if (batchId && store.isDuplicate(batchId, developer)) {
        json(res, 200, { status: "ok", duplicate: true, entryCount: 0 });
        return;
      }

      const result = store.saveBatch({
        batchId,
        developer,
        machine: String(batch.machine ?? "unknown"),
        agent: String(batch.agent ?? "unknown"),
        project: String(batch.project ?? "unknown"),
        sourceFile: String(batch.sourceFile ?? ""),
        shippedAt: String(batch.shippedAt ?? ""),
        receivedAt: new Date().toISOString(),
        entries: entries.map(String),
      });

      json(res, 200, { status: "ok", entryCount: result.entryCount });
      return;
    }

    // 404
    json(res, 404, { error: "Not found" });
  });

  return new Promise((resolve) => {
    server.listen(config.port, () => resolve(server));
  });
}
