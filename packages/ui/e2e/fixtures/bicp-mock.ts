import { test as base, type Page, type Route } from "@playwright/test";
import * as mockData from "./mock-data";

type BICPHandler = (params: Record<string, unknown>) => unknown;

interface JSONRPCRequest {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
  id: string | number;
}

interface CallRecord {
  method: string;
  params: Record<string, unknown> | undefined;
  timestamp: number;
}

/**
 * BICPMock intercepts all POST /bicp requests at the network level
 * and returns configurable JSON-RPC responses.
 *
 * Default happy-path handlers are pre-configured. Tests override
 * individual methods via `.on()` or `.onError()`.
 */
export class BICPMock {
  private handlers = new Map<string, BICPHandler>();
  private calls: CallRecord[] = [];

  constructor() {
    this.resetToDefaults();
  }

  /** Reset all handlers to default happy-path responses. */
  resetToDefaults(): void {
    this.handlers.clear();
    this.calls = [];

    // Initialize
    this.on("initialize", () => mockData.INITIALIZE_RESULT);

    // Connections
    this.on("connections/list", () => mockData.CONNECTIONS_HAPPY);
    this.on("connections/get", () => mockData.CONNECTION_GET_PRODUCTION);
    this.on("connections/test", () => mockData.CONNECTION_TEST_SUCCESS);
    this.on("connections/create", () => mockData.CONNECTION_CREATE_SUCCESS);
    this.on("connections/update", () => mockData.CONNECTION_UPDATE_SUCCESS);
    this.on("connections/delete", () => mockData.CONNECTION_DELETE_SUCCESS);
    this.on("connections/switch", () => mockData.CONNECTION_SWITCH_SUCCESS);
    this.on("connections/sync", () => mockData.CONNECTION_SYNC_SUCCESS);
    this.on("connections/discover", () => mockData.CONNECTION_DISCOVER_SUCCESS);

    // Context
    this.on("context/tree", () => mockData.CONTEXT_TREE_HAPPY);
    this.on("context/read", (params) => {
      const path = params?.path as string | undefined;
      if (path && path.includes("/")) {
        return mockData.CONTEXT_READ_YAML;
      }
      return mockData.CONTEXT_READ_STOCK_README;
    });
    this.on("context/write", () => mockData.CONTEXT_WRITE_SUCCESS);
    this.on("context/create", () => mockData.CONTEXT_CREATE_SUCCESS);
    this.on("context/delete", () => mockData.CONTEXT_DELETE_SUCCESS);

    // Git
    this.on("context/git/history", () => mockData.GIT_HISTORY_HAPPY);
    this.on("context/git/show", () => mockData.GIT_SHOW_RESULT);
    this.on("context/git/revert", () => mockData.GIT_REVERT_SUCCESS);

    // Traces
    this.on("traces/list", () => mockData.TRACES_SIMPLE);
    this.on("traces/dates", () => mockData.TRACES_DATES_HAPPY);
    this.on("traces/clear", () => mockData.TRACES_CLEAR_SUCCESS);

    // Insights
    this.on("insights/analyze", () => mockData.INSIGHTS_HAPPY);

    // Rules
    this.on("context/add-rule", () => mockData.ADD_RULE_SUCCESS);
    this.on("gaps/dismiss", () => mockData.DISMISS_GAP_SUCCESS);
    this.on("insights/save-example", () => mockData.SAVE_EXAMPLE_SUCCESS);

    // Metrics & Dimensions
    this.on("metrics/list", () => mockData.METRICS_LIST_HAPPY);
    this.on("metrics/add", () => mockData.METRICS_ADD_SUCCESS);
    this.on("metrics/update", () => mockData.METRICS_UPDATE_SUCCESS);
    this.on("metrics/delete", () => mockData.METRICS_DELETE_SUCCESS);
    this.on("metrics/candidates", () => mockData.METRICS_CANDIDATES_HAPPY);
    this.on("metrics/approve", () => mockData.METRICS_APPROVE_SUCCESS);
  }

  /** Register a handler for a BICP method. */
  on(method: string, handler: BICPHandler): void {
    this.handlers.set(method, handler);
  }

  /** Register an error response for a BICP method. */
  onError(method: string, code: number, message: string): void {
    this.handlers.set(method, () => {
      throw { code, message };
    });
  }

  /** Get all recorded calls, optionally filtered by method. */
  getCalls(method?: string): CallRecord[] {
    if (method) {
      return this.calls.filter((c) => c.method === method);
    }
    return [...this.calls];
  }

  /** Get the last call for a method, or undefined. */
  getLastCall(method: string): CallRecord | undefined {
    const methodCalls = this.getCalls(method);
    return methodCalls[methodCalls.length - 1];
  }

  /** Clear recorded calls. */
  clearCalls(): void {
    this.calls = [];
  }

  /** Install route handler on a Playwright page. Call before page.goto(). */
  async install(page: Page): Promise<void> {
    await page.route("**/bicp", async (route: Route) => {
      const request = route.request();
      if (request.method() !== "POST") {
        await route.continue();
        return;
      }

      let body: JSONRPCRequest;
      try {
        body = JSON.parse(request.postData() || "{}");
      } catch {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            jsonrpc: "2.0",
            error: { code: -32700, message: "Parse error" },
            id: null,
          }),
        });
        return;
      }

      // Record the call
      this.calls.push({
        method: body.method,
        params: body.params,
        timestamp: Date.now(),
      });

      const handler = this.handlers.get(body.method);
      if (!handler) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            jsonrpc: "2.0",
            error: {
              code: -32601,
              message: `Method not found: ${body.method}`,
            },
            id: body.id,
          }),
        });
        return;
      }

      try {
        const result = handler(body.params || {});
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            jsonrpc: "2.0",
            result,
            id: body.id,
          }),
        });
      } catch (err: unknown) {
        const error = err as { code?: number; message?: string };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            jsonrpc: "2.0",
            error: {
              code: error.code || -32603,
              message: error.message || "Internal error",
            },
            id: body.id,
          }),
        });
      }
    });
  }
}

// ── Playwright fixture ──────────────────────────────────────

interface BICPFixtures {
  bicpMock: BICPMock;
}

/**
 * Extended Playwright `test` with auto-injected `bicpMock` fixture.
 * The mock is installed before each test and reset between tests.
 *
 * Usage:
 *   import { test, expect } from "./fixtures";
 *   test("my test", async ({ page, bicpMock }) => { ... });
 */
export const test = base.extend<BICPFixtures>({
  bicpMock: [
    async ({ page }, use) => {
      const mock = new BICPMock();
      await mock.install(page);
      await use(mock);
    },
    { auto: true },
  ],
});
