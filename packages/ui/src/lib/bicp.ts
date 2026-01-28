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

// Schema Explorer types
export interface SchemaInfo {
  name: string;
  catalog: string | null;
  tableCount: number | null;
}

export interface TableInfo {
  name: string;
  description: string | null;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  description: string | null;
  isPrimaryKey: boolean;
}

export interface CatalogsResult {
  success: boolean;
  catalogs: string[];
  error?: string;
}

export interface SchemasResult {
  success: boolean;
  schemas: SchemaInfo[];
  error?: string;
}

export interface TablesResult {
  success: boolean;
  tables: TableInfo[];
  error?: string;
}

export interface ColumnsResult {
  success: boolean;
  columns: ColumnInfo[];
  error?: string;
}

export interface ValidateLinkResult {
  success: boolean;
  valid: boolean;
  parsed: {
    catalog: string | null;
    schema: string | null;
    table: string | null;
    column: string | null;
  };
  error?: string;
}

// Schema API functions
export async function getCatalogs(): Promise<CatalogsResult> {
  return bicpCall<CatalogsResult>("schema/catalogs", {});
}

export async function getSchemas(catalog?: string): Promise<SchemasResult> {
  return bicpCall<SchemasResult>("schema/schemas", { catalog });
}

export async function getTables(
  schema: string,
  catalog?: string,
): Promise<TablesResult> {
  return bicpCall<TablesResult>("schema/tables", { schema, catalog });
}

export async function getColumns(
  table: string,
  schema?: string,
  catalog?: string,
): Promise<ColumnsResult> {
  return bicpCall<ColumnsResult>("schema/columns", { table, schema, catalog });
}

export async function validateLink(link: string): Promise<ValidateLinkResult> {
  return bicpCall<ValidateLinkResult>("schema/validate-link", { link });
}

// Git History types
export interface GitCommit {
  hash: string;
  fullHash: string;
  message: string;
  date: string;
  author: string;
}

export interface GitHistoryResult {
  success: boolean;
  commits?: GitCommit[];
  error?: string;
}

export interface GitShowResult {
  success: boolean;
  content?: string;
  commit?: string;
  error?: string;
}

export interface GitRevertResult {
  success: boolean;
  newCommit?: string;
  error?: string;
}

// Git history API functions
export async function getGitHistory(
  connection: string,
  path: string,
  limit: number = 50,
): Promise<GitHistoryResult> {
  return bicpCall<GitHistoryResult>("context/git/history", {
    connection,
    path,
    limit,
  });
}

export async function getGitShow(
  connection: string,
  path: string,
  commit: string,
): Promise<GitShowResult> {
  return bicpCall<GitShowResult>("context/git/show", {
    connection,
    path,
    commit,
  });
}

export async function revertToCommit(
  connection: string,
  path: string,
  commit: string,
): Promise<GitRevertResult> {
  return bicpCall<GitRevertResult>("context/git/revert", {
    connection,
    path,
    commit,
  });
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
