import { Readable, Writable } from "node:stream";
import type { JsonRpcNotification, JsonRpcRequest } from "../types/index.js";
import { isJsonRpcResponse, isJsonRpcNotification, isJsonRpcRequest } from "../types/index.js";
import { parseNdjsonStream } from "./stream.js";

export type RequestHandler = (method: string, params: unknown) => Promise<unknown>;

export interface RpcClient {
  sendRequest: (method: string, params?: unknown, options?: RequestOptions) => Promise<unknown>;
  sendNotification: (method: string, params?: unknown) => void;
  sendResponse: (id: number | string, result: unknown) => void;
  sendErrorResponse: (id: number | string, code: number, message: string) => void;
  /** Register a notification handler. Returns an unsubscribe function. Multiple handlers are supported. */
  onNotification: (handler: (notification: JsonRpcNotification) => void) => () => void;
  /** Register a request handler. Returns an unsubscribe function. Handlers are tried in order; first to not throw wins. */
  onRequest: (handler: RequestHandler) => () => void;
  destroy: () => void;
}

export interface RequestOptions {
  timeout?: number | null;
  inactivityTimeout?: number | null;
  activityKey?: string;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
  timeoutTimer: ReturnType<typeof setTimeout> | null;
  inactivityTimer: ReturnType<typeof setTimeout> | null;
  timeoutMs: number | null;
  inactivityTimeoutMs: number | null;
  activityKey?: string;
  method: string;
  id: number | string;
}

export const createRpcClient = (
  input: Readable,
  output: Writable,
  options?: { timeout?: number },
): RpcClient => {
  const timeout = options?.timeout ?? 30_000;
  let nextId = 1;

  const pending = new Map<number | string, PendingRequest>();

  const notificationHandlers: Array<(notification: JsonRpcNotification) => void> = [];
  const requestHandlers: RequestHandler[] = [];

  const clearPendingTimers = (entry: PendingRequest): void => {
    if (entry.timeoutTimer) {
      clearTimeout(entry.timeoutTimer);
      entry.timeoutTimer = null;
    }
    if (entry.inactivityTimer) {
      clearTimeout(entry.inactivityTimer);
      entry.inactivityTimer = null;
    }
  };

  const startInactivityTimer = (entry: PendingRequest): void => {
    if (entry.inactivityTimeoutMs === null || entry.inactivityTimeoutMs <= 0) return;
    if (entry.inactivityTimer) {
      clearTimeout(entry.inactivityTimer);
    }
    entry.inactivityTimer = setTimeout(() => {
      pending.delete(entry.id);
      entry.inactivityTimer = null;
      entry.reject(new Error(
        `RPC request "${entry.method}" (id=${entry.id}) timed out after ${entry.inactivityTimeoutMs}ms of inactivity`,
      ));
    }, entry.inactivityTimeoutMs);
  };

  const touchActivity = (activityKey: string | undefined): void => {
    if (!activityKey) return;
    for (const entry of pending.values()) {
      if (entry.activityKey !== activityKey) continue;
      startInactivityTimer(entry);
    }
  };

  const extractActivityKey = (msg: unknown): string | undefined => {
    if (!msg || typeof msg !== "object") return undefined;
    const params = (msg as { params?: unknown }).params;
    if (!params || typeof params !== "object") return undefined;
    const sessionId = (params as { sessionId?: unknown }).sessionId;
    return typeof sessionId === "string" && sessionId.length > 0 ? sessionId : undefined;
  };

  /** Try each request handler in order. First one that resolves wins. */
  const dispatchRequest = async (method: string, params: unknown): Promise<unknown> => {
    let lastError: unknown;
    for (const handler of requestHandlers) {
      try {
        return await handler(method, params);
      } catch (err) {
        lastError = err;
        continue;
      }
    }
    throw lastError ?? new Error(`No handler for method: ${method}`);
  };

  const handleMessage = (msg: unknown): void => {
    if (isJsonRpcRequest(msg)) {
      const req = msg as JsonRpcRequest;
      touchActivity(extractActivityKey(req));
      console.log(`[rpc] Incoming request: id=${req.id}, method=${req.method}`);
      if (requestHandlers.length > 0) {
        dispatchRequest(req.method, req.params).then(
          (result) => {
            console.log(`[rpc] Sending response for id=${req.id}: ${JSON.stringify(result).slice(0, 200)}`);
            sendResponse(req.id, result);
          },
          (err: unknown) => {
            console.log(`[rpc] Sending error response for id=${req.id}: ${err instanceof Error ? err.message : "Unknown error"}`);
            sendErrorResponse(req.id, -32000, err instanceof Error ? err.message : "Unknown error");
          },
        );
      } else {
        sendErrorResponse(req.id, -32601, `Method not found: ${req.method}`);
      }
      return;
    }

    if (isJsonRpcNotification(msg)) {
      const notif = msg as JsonRpcNotification;
      touchActivity(extractActivityKey(notif));
      console.log(`[rpc] Incoming notification: method=${notif.method}`);
      for (const handler of notificationHandlers) {
        handler(notif);
      }
      return;
    }

    if (isJsonRpcResponse(msg)) {
      const resp = msg as { id: unknown };
      console.log(`[rpc] Incoming response: id=${resp.id}`);
      const entry = pending.get(resp.id as number | string);
      if (!entry) {
        console.log(`[rpc] No pending entry for id=${resp.id}`);
        return;
      }
      pending.delete(msg.id as number | string);
      clearPendingTimers(entry);

      if (msg.error) {
        entry.reject(new Error(msg.error.message));
      } else {
        entry.resolve(msg.result);
      }
    }
  };

  parseNdjsonStream(input, handleMessage, () => {});

  const sendRequest = (method: string, params?: unknown, requestOptions?: RequestOptions): Promise<unknown> => {
    const id = nextId++;
    const request: Record<string, unknown> = { jsonrpc: "2.0", id, method };
    if (params !== undefined) request.params = params;

    console.log(`[rpc] Sending request: id=${id}, method=${method}`);
    output.write(JSON.stringify(request) + "\n");

    return new Promise<unknown>((resolve, reject) => {
      const timeoutMs = requestOptions?.timeout === undefined ? timeout : requestOptions.timeout;
      const inactivityTimeoutMs = requestOptions?.inactivityTimeout ?? null;
      const entry: PendingRequest = {
        resolve,
        reject,
        timeoutTimer: null,
        inactivityTimer: null,
        timeoutMs,
        inactivityTimeoutMs,
        activityKey: requestOptions?.activityKey,
        method,
        id,
      };

      if (timeoutMs !== null && timeoutMs > 0) {
        entry.timeoutTimer = setTimeout(() => {
          pending.delete(id);
          entry.timeoutTimer = null;
          reject(new Error(`RPC request "${method}" (id=${id}) timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      }

      pending.set(id, entry);
      startInactivityTimer(entry);
    });
  };

  const sendNotification = (method: string, params?: unknown): void => {
    const notification: Record<string, unknown> = { jsonrpc: "2.0", method };
    if (params !== undefined) notification.params = params;
    output.write(JSON.stringify(notification) + "\n");
  };

  const sendResponse = (id: number | string, result: unknown): void => {
    output.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
  };

  const sendErrorResponse = (id: number | string, code: number, message: string): void => {
    output.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n");
  };

  const onNotification = (handler: (notification: JsonRpcNotification) => void): (() => void) => {
    notificationHandlers.push(handler);
    return () => {
      const idx = notificationHandlers.indexOf(handler);
      if (idx !== -1) notificationHandlers.splice(idx, 1);
    };
  };

  const onRequest = (handler: RequestHandler): (() => void) => {
    requestHandlers.push(handler);
    return () => {
      const idx = requestHandlers.indexOf(handler);
      if (idx !== -1) requestHandlers.splice(idx, 1);
    };
  };

  const destroy = (): void => {
    for (const [, entry] of pending) {
      clearPendingTimers(entry);
    }
    pending.clear();
  };

  return { sendRequest, sendNotification, sendResponse, sendErrorResponse, onNotification, onRequest, destroy };
};
