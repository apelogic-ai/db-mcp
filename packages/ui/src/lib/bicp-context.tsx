"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  ReactNode,
} from "react";

// JSON-RPC 2.0 Types
interface JSONRPCRequest {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
  id: number;
}

interface JSONRPCResponse<T = unknown> {
  jsonrpc: "2.0";
  result?: T;
  error?: { code: number; message: string; data?: unknown };
  id: number | null;
}

export interface BICPServerInfo {
  name: string;
  version: string;
  protocolVersion: string;
}

interface BICPContextValue {
  isInitialized: boolean;
  isLoading: boolean;
  error: Error | null;
  serverInfo: BICPServerInfo | null;
  initialize: () => Promise<void>;
  call: <T = unknown>(
    method: string,
    params?: Record<string, unknown>
  ) => Promise<T>;
}

const BICPContext = createContext<BICPContextValue | null>(null);

let requestId = 0;

interface BICPProviderProps {
  children: ReactNode;
  baseUrl?: string;
  autoConnect?: boolean;
}

export function BICPProvider({
  children,
  baseUrl = "/bicp",
  autoConnect = true,
}: BICPProviderProps) {
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [serverInfo, setServerInfo] = useState<BICPServerInfo | null>(null);

  const call = useCallback(
    async <T = unknown>(
      method: string,
      params?: Record<string, unknown>
    ): Promise<T> => {
      const request: JSONRPCRequest = {
        jsonrpc: "2.0",
        method,
        params,
        id: ++requestId,
      };

      const response = await fetch(baseUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status} ${response.statusText}`);
      }

      const jsonResponse: JSONRPCResponse<T> = await response.json();

      if (jsonResponse.error) {
        throw new Error(
          `BICP error ${jsonResponse.error.code}: ${jsonResponse.error.message}`
        );
      }

      return jsonResponse.result as T;
    },
    [baseUrl]
  );

  const initialize = useCallback(async () => {
    if (isLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await call<{
        serverInfo: BICPServerInfo;
        protocolVersion: string;
      }>("initialize", {
        protocolVersion: "0.1.0",
        clientInfo: { name: "db-mcp-ui", version: "0.1.0" },
        capabilities: {
          streaming: true,
          candidateSelection: true,
          semanticSearch: true,
          refinement: true,
        },
      });
      setServerInfo(result.serverInfo);
      setIsInitialized(true);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setIsInitialized(false);
    } finally {
      setIsLoading(false);
    }
  }, [call, isLoading]);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect && !isInitialized && !isLoading) {
      initialize();
    }
  }, [autoConnect, isInitialized, isLoading, initialize]);

  return (
    <BICPContext.Provider
      value={{
        isInitialized,
        isLoading,
        error,
        serverInfo,
        initialize,
        call,
      }}
    >
      {children}
    </BICPContext.Provider>
  );
}

export function useBICP(): BICPContextValue {
  const context = useContext(BICPContext);
  if (!context) {
    throw new Error("useBICP must be used within a BICPProvider");
  }
  return context;
}
