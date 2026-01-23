"use client";

import { useState, useCallback, useMemo } from "react";

// JSON-RPC 2.0 Types
export interface JSONRPCRequest {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
  id: string | number;
}

export interface JSONRPCResponse<T = unknown> {
  jsonrpc: "2.0";
  result?: T;
  error?: JSONRPCError;
  id: string | number | null;
}

export interface JSONRPCError {
  code: number;
  message: string;
  data?: unknown;
}

// BICP-specific types
export interface BICPClientInfo {
  name: string;
  version: string;
}

export interface BICPServerInfo {
  name: string;
  version: string;
  protocolVersion: string;
}

export interface InitializeParams {
  protocolVersion: string;
  clientInfo: BICPClientInfo;
  capabilities?: Record<string, unknown>;
}

export interface InitializeResult {
  protocolVersion: string;
  serverInfo: BICPServerInfo;
  capabilities: Record<string, unknown>;
}

// BICP Client Configuration
export interface BICPConfig {
  baseUrl: string;
  clientName: string;
  clientVersion: string;
}

const DEFAULT_CONFIG: BICPConfig = {
  baseUrl: "/bicp",
  clientName: "db-mcp-ui",
  clientVersion: "0.1.0",
};

let requestId = 0;

function nextRequestId(): number {
  return ++requestId;
}

// Core BICP call function
export async function bicpCall<T = unknown>(
  method: string,
  params?: Record<string, unknown>,
  config: Partial<BICPConfig> = {},
): Promise<T> {
  const finalConfig = { ...DEFAULT_CONFIG, ...config };

  const request: JSONRPCRequest = {
    jsonrpc: "2.0",
    method,
    params,
    id: nextRequestId(),
  };

  const response = await fetch(finalConfig.baseUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`HTTP error: ${response.status} ${response.statusText}`);
  }

  const jsonResponse: JSONRPCResponse<T> = await response.json();

  if (jsonResponse.error) {
    throw new Error(
      `BICP error ${jsonResponse.error.code}: ${jsonResponse.error.message}`,
    );
  }

  return jsonResponse.result as T;
}

// Initialize the BICP connection
export async function initialize(
  config: Partial<BICPConfig> = {},
): Promise<InitializeResult> {
  const finalConfig = { ...DEFAULT_CONFIG, ...config };

  const params: InitializeParams = {
    protocolVersion: "0.1.0",
    clientInfo: {
      name: finalConfig.clientName,
      version: finalConfig.clientVersion,
    },
    capabilities: {
      streaming: true,
      candidateSelection: true,
      semanticSearch: true,
      refinement: true,
    },
  };

  return bicpCall<InitializeResult>(
    "initialize",
    params as unknown as Record<string, unknown>,
    config,
  );
}

// React hook for BICP operations
export interface UseBICPResult {
  isInitialized: boolean;
  isLoading: boolean;
  error: Error | null;
  serverInfo: BICPServerInfo | null;
  initialize: () => Promise<void>;
  call: <T = unknown>(
    method: string,
    params?: Record<string, unknown>,
  ) => Promise<T>;
}

export function useBICP(config: Partial<BICPConfig> = {}): UseBICPResult {
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [serverInfo, setServerInfo] = useState<BICPServerInfo | null>(null);

  // Memoize config to prevent unnecessary re-renders
  const stableConfig = useMemo(
    () => ({ ...DEFAULT_CONFIG, ...config }),
    [config.baseUrl, config.clientName, config.clientVersion],
  );

  const initializeConnection = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await initialize(stableConfig);
      setServerInfo(result.serverInfo);
      setIsInitialized(true);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setIsInitialized(false);
    } finally {
      setIsLoading(false);
    }
  }, [stableConfig]);

  const call = useCallback(
    async <T = unknown>(
      method: string,
      params?: Record<string, unknown>,
    ): Promise<T> => {
      return bicpCall<T>(method, params, stableConfig);
    },
    [stableConfig],
  );

  return {
    isInitialized,
    isLoading,
    error,
    serverInfo,
    initialize: initializeConnection,
    call,
  };
}
