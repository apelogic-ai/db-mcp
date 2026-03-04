export interface Connection {
  name: string;
  isActive: boolean;
  hasSchema: boolean;
  hasDomain: boolean;
  hasCredentials: boolean;
  dialect: string | null;
  onboardingPhase: string | null;
  connectorType: "sql" | "file" | "api";
}

export interface ConnectionsListResult {
  connections: Connection[];
  activeConnection: string | null;
}

export interface CreateResult {
  success: boolean;
  name?: string;
  dialect?: string;
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

export interface DeleteResult {
  success: boolean;
  error?: string;
}

export interface GetResult {
  success: boolean;
  name?: string;
  databaseUrl?: string;
  connectorType?: "sql" | "file" | "api";
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

export interface UpdateResult {
  success: boolean;
  error?: string;
}

export type ConnectArgs = Record<string, string | boolean | number>;

export interface ConnectionTestStatus {
  testing: boolean;
  success: boolean | null;
  message: string;
  hint?: string;
}
