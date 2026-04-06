// ACP protocol types (JSON-RPC 2.0 + ACP session updates)

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number | string;
  method: string;
  params?: unknown;
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | string | null;
  result?: unknown;
  error?: JsonRpcError;
}

export interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
}

export type JsonRpcMessage = JsonRpcRequest | JsonRpcResponse | JsonRpcNotification;

export type AcpSessionUpdateType =
  | "agent_message_chunk"
  | "agent_thought_chunk"
  | "tool_call"
  | "tool_call_update"
  | "plan"
  | "user_message_chunk"
  | "available_commands_update"
  | "current_mode_update";

export type ToolCallStatus = "pending" | "in_progress" | "completed" | "failed" | "cancelled";

export type PermissionOptionKind = "allow_once" | "allow_always" | "reject_once" | "reject_always";

export interface AcpPermissionOption {
  optionId: string;
  name: string;
  kind: PermissionOptionKind;
}

export interface AcpPermissionRequest {
  options: AcpPermissionOption[];
  tool: string;
  description: string;
}

export type AcpPermissionOutcome =
  | { outcome: "selected"; optionId: string }
  | { outcome: "cancelled" };

export const isJsonRpcRequest = (value: unknown): value is JsonRpcRequest => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return obj.jsonrpc === "2.0" && typeof obj.method === "string" && "id" in obj;
};

export const isJsonRpcResponse = (value: unknown): value is JsonRpcResponse => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return obj.jsonrpc === "2.0" && "id" in obj && !("method" in obj);
};

export const isJsonRpcNotification = (value: unknown): value is JsonRpcNotification => {
  if (typeof value !== "object" || value === null) return false;
  const obj = value as Record<string, unknown>;
  return obj.jsonrpc === "2.0" && typeof obj.method === "string" && !("id" in obj);
};

export const parseAcpLine = (line: string): JsonRpcMessage => {
  const parsed = JSON.parse(line);
  if (isJsonRpcRequest(parsed)) return parsed;
  if (isJsonRpcResponse(parsed)) return parsed;
  if (isJsonRpcNotification(parsed)) return parsed;
  throw new Error(`Invalid ACP message: ${line}`);
};
