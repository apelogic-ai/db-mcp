import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  bicpCall,
  initialize,
  getCatalogs,
  getSchemas,
  getTables,
  getColumns,
  validateLink,
  getGitHistory,
  getGitShow,
  revertToCommit,
} from "@/lib/bicp";

// Mock fetch globally
const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal("fetch", mockFetch);
});

describe("bicpCall", () => {
  it("sends a JSON-RPC 2.0 request and returns result", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jsonrpc: "2.0",
        result: { success: true, data: "hello" },
        id: 1,
      }),
    });

    const result = await bicpCall<{ success: boolean; data: string }>(
      "test/method",
      { key: "value" },
    );

    expect(result).toEqual({ success: true, data: "hello" });

    // Verify fetch was called correctly
    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe("/bicp");
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");

    const body = JSON.parse(options.body);
    expect(body.jsonrpc).toBe("2.0");
    expect(body.method).toBe("test/method");
    expect(body.params).toEqual({ key: "value" });
    expect(body.id).toBeTypeOf("number");
  });

  it("throws on HTTP error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
    });

    await expect(bicpCall("test/method")).rejects.toThrow(
      "HTTP error: 500 Internal Server Error",
    );
  });

  it("throws on JSON-RPC error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jsonrpc: "2.0",
        error: { code: -32600, message: "Invalid Request" },
        id: 1,
      }),
    });

    await expect(bicpCall("test/method")).rejects.toThrow(
      "BICP error -32600: Invalid Request",
    );
  });

  it("sends request without params when none provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jsonrpc: "2.0",
        result: "ok",
        id: 1,
      }),
    });

    await bicpCall("test/method");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.params).toBeUndefined();
  });

  it("uses custom baseUrl from config", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jsonrpc: "2.0",
        result: "ok",
        id: 1,
      }),
    });

    await bicpCall("test/method", undefined, {
      baseUrl: "http://localhost:8080/bicp",
    });

    expect(mockFetch.mock.calls[0][0]).toBe("http://localhost:8080/bicp");
  });

  it("increments request ID across calls", async () => {
    const makeResponse = () => ({
      ok: true,
      json: async () => ({ jsonrpc: "2.0", result: "ok", id: 1 }),
    });

    mockFetch.mockResolvedValueOnce(makeResponse());
    mockFetch.mockResolvedValueOnce(makeResponse());

    await bicpCall("method1");
    await bicpCall("method2");

    const body1 = JSON.parse(mockFetch.mock.calls[0][1].body);
    const body2 = JSON.parse(mockFetch.mock.calls[1][1].body);
    expect(body2.id).toBeGreaterThan(body1.id);
  });
});

describe("initialize", () => {
  it("sends initialize request with client info and capabilities", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        jsonrpc: "2.0",
        result: {
          protocolVersion: "0.1.0",
          serverInfo: {
            name: "db-mcp",
            version: "0.4.0",
            protocolVersion: "0.1.0",
          },
          capabilities: {},
        },
        id: 1,
      }),
    });

    const result = await initialize();

    expect(result.protocolVersion).toBe("0.1.0");
    expect(result.serverInfo.name).toBe("db-mcp");

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.method).toBe("initialize");
    expect(body.params.protocolVersion).toBe("0.1.0");
    expect(body.params.clientInfo.name).toBe("db-mcp-ui");
    expect(body.params.capabilities).toBeDefined();
  });
});
