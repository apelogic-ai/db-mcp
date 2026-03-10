export type ConnectorType = "sql" | "file" | "api";

export interface ConnectionRecord {
  name: string;
  isActive: boolean;
  hasSchema: boolean;
  hasDomain: boolean;
  hasCredentials: boolean;
  dialect: string | null;
  onboardingPhase: string | null;
  connectorType: ConnectorType;
}

export interface ConnectionsListResult {
  connections: ConnectionRecord[];
  activeConnection: string | null;
}

export interface ConnectionGetResult {
  success: boolean;
  name?: string;
  databaseUrl?: string;
  connectorType?: ConnectorType;
  directory?: string;
  baseUrl?: string;
  auth?: {
    type: string;
    tokenEnv: string;
    headerName: string;
    paramName: string;
  };
  endpoints?: Array<{ name: string; path: string; method: string }>;
  pagination?: {
    type: string;
    cursorParam: string;
    cursorField: string;
    pageSizeParam: string;
    pageSize: number;
    dataField: string;
  };
  rateLimitRps?: number;
  error?: string;
}

export interface CreateResult {
  success: boolean;
  name?: string;
  dialect?: string;
  error?: string;
}

export interface UpdateResult {
  success: boolean;
  error?: string;
}

export interface DeleteResult {
  success: boolean;
  error?: string;
}

export interface TestResult {
  success: boolean;
  message?: string;
  dialect?: string;
  error?: string;
  hint?: string;
  sources?: Record<string, string>;
}

export interface ConnectionTestStatus {
  testing: boolean;
  success: boolean | null;
  message: string;
  hint?: string;
}

export type ConnectArgs = Record<string, string | boolean | number>;

export type WizardStep = "connect" | "discover" | "sample";

export interface DiscoverySummary {
  status: "idle" | "loading" | "success" | "partial" | "error";
  connectorType: ConnectorType;
  catalogCount?: number;
  schemaCount?: number;
  tableCount?: number;
  endpointCount?: number;
  sampleTargets?: Array<{
    catalog?: string | null;
    schema?: string | null;
    table?: string | null;
    label: string;
  }>;
  endpoints?: Array<{ name: string; path: string; fields?: number }>;
  logs: string[];
  errors: string[];
}

export interface SampleTableResult {
  table_name: string;
  schema?: string | null;
  catalog?: string | null;
  full_name: string;
  rows: Array<Record<string, unknown>>;
  row_count: number;
  limit: number;
  error?: string | null;
}

export interface ContextTreeConnection {
  name: string;
  folders: Array<{
    name: string;
    path: string;
    isEmpty: boolean;
    importance: string;
    hasReadme: boolean;
    files: Array<{ name: string; path: string }>;
  }>;
}
