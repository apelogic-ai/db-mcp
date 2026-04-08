import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createServer, type Server, type IncomingMessage, type ServerResponse } from "node:http";
import { createHttpShipper } from "../src/http-shipper";
import type { ShippedBatch } from "../src/shipper";

let server: Server | null = null;
let received: { body: string; headers: Record<string, string> }[] = [];
let responseStatus = 200;

function startTestServer(port: number): Promise<void> {
  received = [];
  responseStatus = 200;
  return new Promise((resolve) => {
    server = createServer((req: IncomingMessage, res: ServerResponse) => {
      let body = "";
      req.on("data", (chunk) => { body += chunk; });
      req.on("end", () => {
        const headers: Record<string, string> = {};
        for (const [k, v] of Object.entries(req.headers)) {
          if (typeof v === "string") headers[k] = v;
        }
        received.push({ body, headers });
        res.writeHead(responseStatus, { "Content-Type": "application/json" });
        res.end(responseStatus === 200 ? '{"status":"ok"}' : "Internal error");
      });
    });
    server.listen(port, () => resolve());
  });
}

function stopTestServer(): Promise<void> {
  return new Promise((resolve) => {
    if (server) {
      server.close(() => resolve());
      server = null;
    } else {
      resolve();
    }
  });
}

describe("createHttpShipper", () => {
  const port = 19876;

  beforeEach(async () => await startTestServer(port));
  afterEach(async () => await stopTestServer());

  it("POSTs batch as JSON to the endpoint", async () => {
    const ship = createHttpShipper({
      endpoint: `http://localhost:${port}/api/ingest`,
    });

    const batch: ShippedBatch = {
      developer: "alice@acme.com",
      machine: "alice-mac",
      agent: "claude_code",
      project: "test-proj",
      sourceFile: "/tmp/session.jsonl",
      shippedAt: "2026-04-08T16:00:00Z",
      entries: ['{"type":"user","text":"hello"}'],
    };

    await ship(batch);

    expect(received).toHaveLength(1);
    const parsed = JSON.parse(received[0].body);
    expect(parsed.developer).toBe("alice@acme.com");
    expect(parsed.agent).toBe("claude_code");
    expect(parsed.entries).toHaveLength(1);
  });

  it("sets content-type and authorization headers", async () => {
    const ship = createHttpShipper({
      endpoint: `http://localhost:${port}/api/ingest`,
      apiKey: "key_test123",
    });

    await ship({
      developer: "bob",
      machine: "bob-pc",
      agent: "codex",
      project: "p",
      sourceFile: "/tmp/f.jsonl",
      shippedAt: "2026-04-08T16:00:00Z",
      entries: ["{}"],
    });

    expect(received[0].headers["content-type"]).toBe("application/json");
    expect(received[0].headers["authorization"]).toBe("Bearer key_test123");
  });

  it("throws on non-2xx response", async () => {
    responseStatus = 500;

    const ship = createHttpShipper({
      endpoint: `http://localhost:${port}/api/ingest`,
    });

    await expect(
      ship({
        developer: "x",
        machine: "m",
        agent: "claude_code",
        project: "p",
        sourceFile: "/tmp/f",
        shippedAt: "2026-04-08T16:00:00Z",
        entries: ["{}"],
      }),
    ).rejects.toThrow(/500/);
  });

  it("includes batch metadata for the ingestor", async () => {
    const ship = createHttpShipper({
      endpoint: `http://localhost:${port}/api/ingest`,
    });

    await ship({
      developer: "carol",
      machine: "carol-laptop",
      agent: "cursor",
      project: "workspace:abc123",
      sourceFile: "/path/to/state.vscdb",
      shippedAt: "2026-04-08T16:30:00Z",
      entries: ['{"msg":1}', '{"msg":2}'],
    });

    const parsed = JSON.parse(received[0].body);
    expect(parsed.machine).toBe("carol-laptop");
    expect(parsed.project).toBe("workspace:abc123");
    expect(parsed.shippedAt).toBe("2026-04-08T16:30:00Z");
    expect(parsed.entries).toHaveLength(2);
  });
});
