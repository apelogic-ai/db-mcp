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

// Context read/write
export interface ContextReadResult {
  success: boolean;
  content?: string;
  isStockReadme?: boolean;
  error?: string;
}

export interface ContextWriteResult {
  success: boolean;
  gitCommit?: boolean;
  error?: string;
}

export async function contextRead(
  connection: string,
  path: string,
): Promise<ContextReadResult> {
  return bicpCall<ContextReadResult>("context/read", { connection, path });
}

export async function contextWrite(
  connection: string,
  path: string,
  content: string,
): Promise<ContextWriteResult> {
  return bicpCall<ContextWriteResult>("context/write", {
    connection,
    path,
    content,
  });
}

export async function contextAddRule(
  connection: string,
  rule: string,
  gapId?: string,
): Promise<{ success: boolean; duplicate?: boolean; error?: string }> {
  return bicpCall<{ success: boolean; duplicate?: boolean; error?: string }>(
    "context/add-rule",
    { connection, rule, gapId },
  );
}

export async function saveExample(
  connection: string,
  sql: string,
  intent: string,
): Promise<{
  success: boolean;
  example_id?: string;
  total_examples?: number;
  error?: string;
}> {
  return bicpCall<{
    success: boolean;
    example_id?: string;
    total_examples?: number;
    error?: string;
  }>("insights/save-example", { connection, sql, intent });
}

export async function dismissGap(
  connection: string,
  gapId: string,
  reason?: string,
): Promise<{ success: boolean; count?: number; error?: string }> {
  return bicpCall<{ success: boolean; count?: number; error?: string }>(
    "gaps/dismiss",
    { connection, gapId, reason },
  );
}

// Traces types
export interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  start_time: number;
  end_time: number | null;
  duration_ms: number | null;
  status: string;
  attributes: Record<string, unknown>;
  events?: Array<{
    name: string;
    timestamp?: number;
    attributes?: Record<string, unknown>;
  }>;
}

export interface Trace {
  trace_id: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  span_count: number;
  root_span: string | null;
  spans: TraceSpan[];
}

export interface TracesListResult {
  success: boolean;
  traces: Trace[];
  source: "live" | "historical";
  error?: string;
}

export interface TracesClearResult {
  success: boolean;
}

export interface TracesDatesResult {
  success: boolean;
  enabled: boolean;
  dates: string[];
}

// Traces API functions
export async function listTraces(
  source: "live" | "historical" = "live",
  date?: string,
  limit: number = 50,
): Promise<TracesListResult> {
  return bicpCall<TracesListResult>("traces/list", { source, date, limit });
}

export async function clearTraces(): Promise<TracesClearResult> {
  return bicpCall<TracesClearResult>("traces/clear", {});
}

export async function getTraceDates(): Promise<TracesDatesResult> {
  return bicpCall<TracesDatesResult>("traces/dates", {});
}

// Insights types
export interface InsightsAnalysis {
  traceCount: number;
  protocolTracesFiltered: number;
  totalDurationMs: number;
  toolUsage: Record<string, number>;
  errors: Array<{
    trace_id: string;
    span_name: string;
    tool: string;
    error: string;
    error_type?: "hard" | "soft";
    timestamp: number;
  }>;
  errorCount: number;
  validationFailures: Array<{
    sql_preview: string;
    rejected_keyword: string | null;
    error_type: string | null;
    error_message: string;
    timestamp: number;
  }>;
  validationFailureCount: number;
  costTiers: Record<string, number>;
  repeatedQueries: Array<{
    sql_preview: string;
    full_sql?: string;
    suggested_intent?: string;
    count: number;
    first_seen: number;
    last_seen: number;
    is_example?: boolean;
    example_id?: string;
  }>;
  tablesReferenced: Record<string, number>;
  knowledgeEvents: Array<{
    tool: string;
    feedback_type: string;
    examples_added: number | null;
    rules_added: number | null;
    timestamp: number;
    intent?: string;
    filename?: string;
  }>;
  knowledgeCaptureCount: number;
  shellCommands: Array<{
    command: string;
    timestamp: number;
    success: boolean;
  }>;
  knowledgeStatus: {
    hasSchema: boolean;
    hasDomain: boolean;
    exampleCount: number;
    ruleCount: number;
  };
  insights: {
    generationCalls: number;
    callsWithExamples: number;
    callsWithRules: number;
    callsWithoutExamples: number;
    exampleHitRate: number | null;
    validateCalls: number;
    validateFailRate: number | null;
    knowledgeCapturesByType: Record<string, number>;
    sessionCount: number;
  };
  vocabularyGaps: Array<{
    id?: string;
    terms: Array<{
      term: string;
      searchCount: number;
      session: string;
      timestamp: number;
    }>;
    totalSearches: number;
    timestamp: number;
    schemaMatches: Array<{
      name: string;
      table?: string;
      description?: string;
      type: "table" | "column";
    }>;
    suggestedRule: string | null;
    status?: "open" | "resolved" | "dismissed";
    source?: "schema_scan" | "traces";
  }>;
}

export interface InsightsAnalyzeResult {
  success: boolean;
  analysis: InsightsAnalysis;
  error?: string;
}

// Insights API functions
export async function analyzeInsights(
  days: number = 7,
): Promise<InsightsAnalyzeResult> {
  return bicpCall<InsightsAnalyzeResult>("insights/analyze", { days });
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
