import { Buffer } from "node:buffer";
import type { GatewayEvent, JsonRpcNotification, PromptImageInput } from "../types/index.js";
import type { RpcClient } from "./rpc.js";

export type AcpEventHandler = (event: GatewayEvent) => void;

export interface AcpSession {
  id: string;
  acpSessionId: string;
  prompt: (text: string, images?: PromptImageInput[]) => Promise<unknown>;
  respondToPermission: (requestId: string, optionId: string) => boolean;
  cancel: () => void;
  onEvent: (handler: AcpEventHandler) => void;
}

// Real ACP session/update notification shape
// { sessionId, update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "..." } } }
export interface AcpSessionUpdate {
  sessionUpdate: string;
  content?: AcpContentBlock | AcpContentBlock[];
  toolCallId?: string;
  title?: string;
  status?: string;
  rawInput?: unknown;
  rawOutput?: unknown;
  kind?: string;
  _meta?: { claudeCode?: { toolName?: string } };
}

export type AcpContentBlock =
  | {
      type: "text";
      text: string;
    }
  | {
      type: "image";
      data: string;
      mimeType: string;
      uri?: string;
    }
  | {
      type: string;
      [key: string]: unknown;
    };

export interface AcpSessionNotificationParams {
  sessionId: string;
  update: AcpSessionUpdate;
}

// Real ACP session/request_permission request shape (this is a JSON-RPC request, not notification)
export interface AcpRequestPermissionParams {
  sessionId: string;
  toolCall: {
    toolCallId: string;
    title: string;
    status?: string;
    kind?: string;
    rawInput?: unknown;
  };
  options: Array<{ optionId: string; name: string; kind: string }>;
}

const extractText = (content?: AcpContentBlock | AcpContentBlock[]): string => {
  if (!content) return "";
  if (Array.isArray(content)) {
    return content
      .filter((b): b is Extract<AcpContentBlock, { type: "text" }> => b.type === "text" && typeof (b as { text?: unknown }).text === "string")
      .map((b) => b.text)
      .join("");
  }
  return content.type === "text" && typeof content.text === "string" ? content.text : "";
};

const extractToolName = (update: AcpSessionUpdate): string => {
  // Zed's agent builds titles like `"${input.query}"` which becomes '"undefined"'
  // when input fields are missing during streaming. Fall back to _meta.claudeCode.toolName
  // and enrich with rawInput details where useful.
  if (update.title && update.title !== '"undefined"') return update.title;
  const baseName = update._meta?.claudeCode?.toolName ?? "unknown";
  // Enrich tool name with key details from rawInput
  const input = update.rawInput as Record<string, unknown> | undefined;
  if (input) {
    if (input.query) return `${baseName}: ${input.query}`;
    if (input.pattern) return `${baseName}: ${input.pattern}`;
    if (input.file_path) return `${baseName}: ${input.file_path}`;
    if (input.command) return `${baseName}: ${String(input.command).slice(0, 80)}`;
  }
  return baseName;
};

export const translateNotification = (
  notification: JsonRpcNotification,
  gatewaySessionId: string,
  acpSessionId: string,
): GatewayEvent | null => {
  if (notification.method !== "session/update") return null;

  const p = notification.params as AcpSessionNotificationParams | undefined;
  if (!p || p.sessionId !== acpSessionId) return null;

  const update = p.update;
  switch (update.sessionUpdate) {
    case "agent_message_chunk":
    case "agent_message": // non-chunked complete message
      return {
        type: "text_delta",
        sessionId: gatewaySessionId,
        delta: extractText(update.content),
      };
    case "agent_thought_chunk":
      return {
        type: "thinking_delta",
        sessionId: gatewaySessionId,
        delta: extractText(update.content),
      };
    case "tool_call":
      return {
        type: "tool_start",
        sessionId: gatewaySessionId,
        tool: extractToolName(update),
        toolCallId: update.toolCallId,
        params: update.rawInput ?? null,
      };
    case "tool_call_update":
      if (update.status === "completed" || update.status === "failed") {
        return {
          type: "tool_end",
          sessionId: gatewaySessionId,
          tool: extractToolName(update),
          toolCallId: update.toolCallId,
          result: update.rawOutput as string | undefined,
        };
      }
      return null;
    default:
      return null;
  }
};

export type PolicyEvaluator = (tool: string, params?: string) => "allow" | "deny" | "ask";

/** Infer the canonical tool name from a permission request's toolCall.
 *  The ACP agent may set `title` to a formatted display string (e.g. a search query)
 *  rather than the actual tool name. We use `kind` and `rawInput` structure to detect. */
const inferToolName = (toolCall: AcpRequestPermissionParams["toolCall"]): string | undefined => {
  // Use the `kind` field if it maps to a known tool type
  const kind = typeof toolCall.kind === "string" ? toolCall.kind.toLowerCase() : undefined;
  if (kind === "fetch") return "WebFetch";
  if (kind === "search" || kind === "web_search") return "WebSearch";
  if (kind === "bash") return "Bash";

  const input = toolCall.rawInput as Record<string, unknown> | undefined;
  if (!input) return undefined;
  // Fallback: match rawInput structure to known Claude Code tool names
  if ("query" in input) return "WebSearch";
  if ("command" in input && !("file_path" in input)) return "Bash";
  if ("url" in input && "prompt" in input) return "WebFetch";
  return undefined;
};

export const createAcpSession = (
  rpc: RpcClient,
  acpSessionId: string,
  gatewaySessionId: string,
  options?: { policyEvaluator?: PolicyEvaluator; promptInactivityTimeoutMs?: number },
): AcpSession => {
  const policyEvaluator = options?.policyEvaluator;
  const promptInactivityTimeoutMs = options?.promptInactivityTimeoutMs ?? 600_000;
  let eventHandler: AcpEventHandler | undefined;

  // Pending permission requests from the agent (request_id → resolver)
  const pendingPermissions = new Map<
    string,
    { resolve: (result: unknown) => void }
  >();

  rpc.onNotification((notification: JsonRpcNotification) => {
    if (!eventHandler) return;
    const event = translateNotification(notification, gatewaySessionId, acpSessionId);
    if (event) {
      console.log(`[acp-session] Emitting event: type=${event.type}${event.type === "text_delta" ? `, delta=${(event as { delta: string }).delta.slice(0, 80)}` : ""}`);
      eventHandler(event);
    } else if (notification.method === "session/update") {
      const p = notification.params as { update?: { sessionUpdate?: string } } | undefined;
      console.log(`[acp-session] Dropped notification: sessionUpdate=${p?.update?.sessionUpdate}`);
    }
  });

  // Handle incoming requests from the agent (permission requests)
  rpc.onRequest(async (method: string, params: unknown) => {
    console.log(`[acp-session] Received request: ${method}`);
    if (method === "session/request_permission") {
      const p = params as AcpRequestPermissionParams;
      if (p.sessionId !== acpSessionId) {
        throw new Error(`Unknown session: ${p.sessionId}`);
      }

      const requestId = p.toolCall.toolCallId;
      const rawToolName = p.toolCall.title;
      const paramsStr = p.toolCall.rawInput ? JSON.stringify(p.toolCall.rawInput) : undefined;
      // Extract canonical tool name — the ACP agent may send a formatted title
      // (e.g., a search query) instead of the actual tool name
      const toolName = inferToolName(p.toolCall) ?? rawToolName;
      const optionKinds = p.options.map((opt) => opt.kind).join(",");
      console.log(`[acp-session] Permission request: requestId=${requestId}, tool=${toolName} (raw: ${rawToolName}, kind: ${p.toolCall.kind}, options=[${optionKinds}])`);

      // Check policy — auto-approve/deny if configured
      if (policyEvaluator) {
        const action = policyEvaluator(toolName, paramsStr);
        if (action === "allow") {
          console.log(`[acp-session] Policy auto-approved: ${toolName}`);
          return { outcome: { outcome: "selected", optionId: "allow_once" } };
        }
        if (action === "deny") {
          console.log(`[acp-session] Policy auto-denied: ${toolName}`);
          return { outcome: { outcome: "selected", optionId: "reject_once" } };
        }
      }

      // Policy says "ask" — forward to the user
      if (eventHandler) {
        eventHandler({
          type: "approval_request",
          sessionId: gatewaySessionId,
          requestId,
          tool: toolName,
          description: paramsStr ?? toolName,
          options: p.options,
        });

        // Wait for the user response via respondToPermission
        return new Promise((resolve) => {
          pendingPermissions.set(requestId, { resolve });
          console.log(`[acp-session] Pending permissions: [${[...pendingPermissions.keys()].join(", ")}]`);
        });
      }

      // No handler — auto-reject
      return { outcome: { outcome: "cancelled" } };
    }

    throw new Error(`Unhandled method: ${method}`);
  });

  const resolveImageBlock = async (image: PromptImageInput): Promise<AcpContentBlock | null> => {
    const url = image.url.trim();
    if (!url) return null;

    // ACP image blocks use binary data (base64), not URL references.
    if (url.startsWith("data:")) {
      const commaIndex = url.indexOf(",");
      if (commaIndex < 0) return null;
      const meta = url.slice(5, commaIndex);
      const payload = url.slice(commaIndex + 1);
      const isBase64 = meta.includes(";base64");
      const mimeTypeFromDataUrl = meta.split(";")[0]?.trim();
      const mimeType = image.mediaType ?? mimeTypeFromDataUrl ?? "image/*";
      const data = isBase64
        ? payload
        : Buffer.from(decodeURIComponent(payload), "utf8").toString("base64");
      return {
        type: "image",
        data,
        mimeType,
      };
    }

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch image URL (${response.status}): ${url}`);
    }
    const mimeType = image.mediaType
      ?? response.headers.get("content-type")?.split(";")[0]?.trim()
      ?? "image/*";
    const arrayBuffer = await response.arrayBuffer();
    const data = Buffer.from(arrayBuffer).toString("base64");
    return {
      type: "image",
      data,
      mimeType,
      uri: url,
    };
  };

  const buildPromptBlocks = async (text: string, images?: PromptImageInput[]): Promise<AcpContentBlock[]> => {
    const imageEntries = (images ?? [])
      .filter((image) => typeof image.url === "string" && image.url.trim().length > 0);
    const imageBlocks: AcpContentBlock[] = [];
    for (const image of imageEntries) {
      try {
        const block = await resolveImageBlock(image);
        if (block) imageBlocks.push(block);
      } catch (error) {
        console.warn(`[acp-session] Failed to resolve image block for ${image.url}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    const needsDefaultText = text.trim().length === 0 && imageBlocks.length > 0;
    const textBlock: AcpContentBlock = {
      type: "text",
      text: needsDefaultText ? "Please analyze the provided image(s)." : text,
    };
    return [textBlock, ...imageBlocks];
  };

  const prompt = async (text: string, images?: PromptImageInput[]): Promise<unknown> => {
    const hasImages = Array.isArray(images) && images.length > 0;
    try {
      const promptBlocks = await buildPromptBlocks(text, images);
      return await rpc.sendRequest("session/prompt", {
        sessionId: acpSessionId,
        prompt: promptBlocks,
      }, {
        timeout: null,
        inactivityTimeout: promptInactivityTimeoutMs,
        activityKey: acpSessionId,
      });
    } catch (error) {
      if (!hasImages) throw error;
      console.warn(`[acp-session] Image blocks rejected by runtime; falling back to URL text prompt: ${error instanceof Error ? error.message : String(error)}`);
      // Compatibility fallback for runtimes that reject image content blocks.
      const fallbackText = [
        text.trim(),
        "",
        "Attached image URLs:",
        ...(images ?? []).map((image, index) => `${index + 1}. ${image.url}`),
      ].join("\n").trim();
      return rpc.sendRequest("session/prompt", {
        sessionId: acpSessionId,
        prompt: [{ type: "text", text: fallbackText }],
      }, {
        timeout: null,
        inactivityTimeout: promptInactivityTimeoutMs,
        activityKey: acpSessionId,
      });
    }
  };

  const respondToPermission = (requestId: string, optionId: string): boolean => {
    const pending = pendingPermissions.get(requestId);
    if (pending) {
      console.log(`[acp-session] Resolving permission: requestId=${requestId}, optionId=${optionId}`);
      pendingPermissions.delete(requestId);
      pending.resolve({ outcome: { outcome: "selected", optionId } });
      return true;
    }
    console.log(`[acp-session] No pending permission for requestId=${requestId} (pending: [${[...pendingPermissions.keys()].join(", ")}])`);
    return false;
  };

  const cancel = (): void => {
    rpc.sendNotification("session/cancel", { sessionId: acpSessionId });
    // Cancel all pending permission requests
    for (const [id, entry] of pendingPermissions) {
      entry.resolve({ outcome: { outcome: "cancelled" } });
      pendingPermissions.delete(id);
    }
  };

  const onEvent = (handler: AcpEventHandler): void => {
    eventHandler = handler;
  };

  return {
    id: gatewaySessionId,
    acpSessionId,
    prompt,
    respondToPermission,
    cancel,
    onEvent,
  };
};
