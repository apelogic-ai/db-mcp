/**
 * Mock response constants for all BICP JSON-RPC methods.
 * Each constant represents a realistic server response.
 */

// ── Initialize ──────────────────────────────────────────────

export const INITIALIZE_RESULT = {
  protocolVersion: "0.1.0",
  serverInfo: {
    name: "db-mcp",
    version: "0.4.12",
    protocolVersion: "0.1.0",
  },
  capabilities: {
    streaming: true,
    candidateSelection: true,
    semanticSearch: true,
    refinement: true,
  },
};

// ── Connections ─────────────────────────────────────────────

export const CONNECTIONS_HAPPY = {
  connections: [
    {
      name: "production",
      isActive: true,
      hasSchema: true,
      hasDomain: true,
      hasCredentials: true,
      dialect: "postgresql",
      onboardingPhase: "complete",
    },
    {
      name: "staging",
      isActive: false,
      hasSchema: true,
      hasDomain: false,
      hasCredentials: true,
      dialect: "clickhouse",
      onboardingPhase: "review",
    },
  ],
  activeConnection: "production",
};

export const CONNECTIONS_EMPTY = {
  connections: [],
  activeConnection: null,
};

export const CONNECTION_GET_PRODUCTION = {
  success: true,
  name: "production",
  databaseUrl: "postgresql://admin:s3cret@db.example.com:5432/analytics",
};

export const CONNECTION_TEST_SUCCESS = {
  success: true,
  dialect: "postgresql",
  message: "Connection successful",
};

export const CONNECTION_TEST_FAILURE = {
  success: false,
  error: 'FATAL: password authentication failed for user "admin"',
};

export const CONNECTION_CREATE_SUCCESS = {
  success: true,
  name: "new-connection",
  dialect: "postgresql",
};

export const CONNECTION_DELETE_SUCCESS = {
  success: true,
};

export const CONNECTION_UPDATE_SUCCESS = {
  success: true,
};

export const CONNECTION_SWITCH_SUCCESS = {
  success: true,
};

export const CONNECTION_SYNC_SUCCESS = {
  success: true,
  synced: ["charges", "customers"],
  rows_fetched: { charges: 150, customers: 42 },
  errors: [],
};

export const CONNECTIONS_WITH_API = {
  connections: [
    {
      name: "production",
      isActive: true,
      hasSchema: true,
      hasDomain: true,
      hasCredentials: true,
      dialect: "postgresql",
      onboardingPhase: "complete",
      connectorType: "sql",
    },
    {
      name: "staging",
      isActive: false,
      hasSchema: true,
      hasDomain: false,
      hasCredentials: true,
      dialect: "clickhouse",
      onboardingPhase: "review",
      connectorType: "sql",
    },
    {
      name: "stripe-api",
      isActive: false,
      hasSchema: false,
      hasDomain: false,
      hasCredentials: true,
      dialect: "duckdb",
      onboardingPhase: null,
      connectorType: "api",
    },
  ],
  activeConnection: "production",
};

export const CONNECTION_GET_API = {
  success: true,
  name: "stripe-api",
  connectorType: "api",
  baseUrl: "https://api.stripe.com/v1",
  auth: {
    type: "bearer",
    tokenEnv: "STRIPE_API_KEY",
    headerName: "Authorization",
    paramName: "api_key",
  },
  endpoints: [
    { name: "charges", path: "/charges", method: "GET" },
    { name: "customers", path: "/customers", method: "GET" },
  ],
  pagination: {
    type: "cursor",
    cursorParam: "starting_after",
    cursorField: "data[-1].id",
    pageSizeParam: "limit",
    pageSize: 100,
    dataField: "data",
  },
  rateLimitRps: 25,
};

// ── Context / Tree ──────────────────────────────────────────

export const CONTEXT_TREE_HAPPY = {
  connections: [
    {
      name: "production",
      isActive: true,
      gitEnabled: true,
      folders: [
        {
          name: "schema",
          path: "schema",
          isEmpty: false,
          importance: "critical",
          hasReadme: true,
          files: [
            { name: "descriptions.yaml", path: "schema/descriptions.yaml" },
          ],
        },
        {
          name: "domain",
          path: "domain",
          isEmpty: false,
          importance: "critical",
          hasReadme: true,
          files: [{ name: "model.yaml", path: "domain/model.yaml" }],
        },
        {
          name: "training",
          path: "training",
          isEmpty: false,
          importance: "recommended",
          hasReadme: true,
          files: [{ name: "examples.yaml", path: "training/examples.yaml" }],
        },
        {
          name: "instructions",
          path: "instructions",
          isEmpty: false,
          importance: "recommended",
          hasReadme: true,
          files: [
            {
              name: "business_rules.yaml",
              path: "instructions/business_rules.yaml",
            },
          ],
        },
        {
          name: "metrics",
          path: "metrics",
          isEmpty: true,
          importance: "optional",
          hasReadme: true,
          files: [],
        },
      ],
    },
    {
      name: "staging",
      isActive: false,
      gitEnabled: false,
      folders: [
        {
          name: "schema",
          path: "schema",
          isEmpty: false,
          importance: "critical",
          hasReadme: true,
          files: [
            { name: "descriptions.yaml", path: "schema/descriptions.yaml" },
          ],
        },
        {
          name: "domain",
          path: "domain",
          isEmpty: true,
          importance: "critical",
          hasReadme: true,
          files: [],
        },
        {
          name: "training",
          path: "training",
          isEmpty: true,
          importance: "recommended",
          hasReadme: true,
          files: [],
        },
        {
          name: "instructions",
          path: "instructions",
          isEmpty: true,
          importance: "recommended",
          hasReadme: true,
          files: [],
        },
        {
          name: "metrics",
          path: "metrics",
          isEmpty: true,
          importance: "optional",
          hasReadme: true,
          files: [],
        },
      ],
    },
  ],
};

export const CONTEXT_TREE_EMPTY = {
  connections: [],
};

// ── Context / File operations ───────────────────────────────

export const CONTEXT_READ_YAML = {
  success: true,
  content: `# Schema Descriptions
tables:
  users:
    description: "Core user accounts table"
    columns:
      id:
        description: "Primary key"
      email:
        description: "User email address"
      created_at:
        description: "Account creation timestamp"
  orders:
    description: "Customer orders"
    columns:
      id:
        description: "Order ID"
      user_id:
        description: "FK to users table"
      total:
        description: "Order total in cents"
`,
  isStockReadme: false,
};

export const CONTEXT_READ_STOCK_README = {
  success: true,
  content: `# Schema

This folder contains schema description files for your database tables and columns.

## Getting Started

Run the onboarding process to auto-generate schema descriptions:
\`\`\`
db-mcp init
\`\`\`
`,
  isStockReadme: true,
};

export const CONTEXT_WRITE_SUCCESS = {
  success: true,
  gitCommit: true,
};

export const CONTEXT_CREATE_SUCCESS = {
  success: true,
  gitCommit: true,
};

export const CONTEXT_DELETE_SUCCESS = {
  success: true,
  gitCommit: true,
};

export const CONTEXT_READ_ERROR = {
  success: false,
  error: "File not found: schema/missing.yaml",
};

// ── Git History ─────────────────────────────────────────────

export const GIT_HISTORY_HAPPY = {
  success: true,
  commits: [
    {
      hash: "abc1234",
      fullHash: "abc1234567890abcdef1234567890abcdef123456",
      message: "Update schema descriptions",
      date: "2025-01-15T10:30:00Z",
      author: "dev@example.com",
    },
    {
      hash: "def5678",
      fullHash: "def5678901234567890abcdef1234567890abcdef",
      message: "Initial schema setup",
      date: "2025-01-10T08:00:00Z",
      author: "dev@example.com",
    },
  ],
};

export const GIT_SHOW_RESULT = {
  success: true,
  content:
    '# Old version of the file\ntables:\n  users:\n    description: "User accounts"\n',
  commit: "def5678",
};

export const GIT_REVERT_SUCCESS = {
  success: true,
  newCommit: "fff9999",
};

// ── Errors ──────────────────────────────────────────────────

export const SERVER_ERROR = {
  code: -32603,
  message: "Internal server error",
};

export const METHOD_NOT_FOUND = {
  code: -32601,
  message: "Method not found",
};

// ── Traces ──────────────────────────────────────────────────

const NOW = Math.floor(Date.now() / 1000);

function makeTrace(
  id: string,
  toolName: string,
  offsetSec: number,
  durationMs: number,
  spanCount: number = 2,
  attrs: Record<string, unknown> = {},
): {
  trace_id: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  span_count: number;
  root_span: string;
  spans: Array<{
    trace_id: string;
    span_id: string;
    parent_span_id: string | null;
    name: string;
    start_time: number;
    end_time: number;
    duration_ms: number;
    status: string;
    attributes: Record<string, unknown>;
  }>;
} {
  const start = NOW - offsetSec;
  return {
    trace_id: id,
    start_time: start,
    end_time: start + durationMs / 1000,
    duration_ms: durationMs,
    span_count: spanCount,
    root_span: toolName,
    spans: [
      {
        trace_id: id,
        span_id: `s-${id}-1`,
        parent_span_id: null,
        name: toolName,
        start_time: start,
        end_time: start + durationMs / 1000,
        duration_ms: durationMs,
        status: "ok",
        attributes: { "tool.name": toolName, ...attrs },
      },
      {
        trace_id: id,
        span_id: `s-${id}-2`,
        parent_span_id: `s-${id}-1`,
        name: toolName,
        start_time: start,
        end_time: start + durationMs / 1000 - 0.001,
        duration_ms: durationMs - 1,
        status: "ok",
        attributes: { "tool.name": toolName },
      },
    ],
  };
}

/** Traces list with a run of consecutive get_result calls for grouping. */
export const TRACES_WITH_POLLING = {
  success: true,
  source: "live" as const,
  traces: [
    // 5 consecutive get_result polls (should be grouped)
    makeTrace("gr-1", "get_result", 10, 0.3),
    makeTrace("gr-2", "get_result", 13, 0.2),
    makeTrace("gr-3", "get_result", 16, 0.3),
    makeTrace("gr-4", "get_result", 19, 0.2),
    makeTrace("gr-5", "get_result", 22, 0.3),
    // execute_query before the polling run
    makeTrace("eq-1", "execute_query", 25, 25700, 4, {
      "sql.preview":
        "SELECT nas_identifier, calling_station_id, count(*) AS re...",
    }),
    // run_sql
    makeTrace("rs-1", "run_sql", 26, 0.3),
    // validate_sql
    makeTrace("vs-1", "validate_sql", 30, 1800, 6, {
      "sql.preview":
        "SELECT nas_identifier, calling_station_id, count(*) AS re...",
    }),
    // 2 more get_result (should NOT be grouped — only 2)
    makeTrace("gr-6", "get_result", 35, 0.3),
    makeTrace("gr-7", "get_result", 38, 0.2),
  ],
};

/** A simple traces result with a few varied tool calls. */
export const TRACES_SIMPLE = {
  success: true,
  source: "live" as const,
  traces: [
    makeTrace("t-1", "get_data", 10, 1200, 3),
    makeTrace("t-2", "validate_sql", 20, 450, 2, {
      "sql.preview": "SELECT * FROM users LIMIT 10",
    }),
    makeTrace("t-3", "shell", 30, 100, 2, {
      command: "cat schema/descriptions.yaml",
    }),
  ],
};

export const TRACES_EMPTY = {
  success: true,
  source: "live" as const,
  traces: [],
};

export const TRACES_DATES_HAPPY = {
  success: true,
  enabled: true,
  dates: [
    new Date().toISOString().slice(0, 10), // today
  ],
};

export const TRACES_DATES_EMPTY = {
  success: true,
  enabled: true,
  dates: [],
};

export const TRACES_CLEAR_SUCCESS = {
  success: true,
};

// Protocol noise traces that should be hidden
export const TRACES_WITH_NOISE = {
  success: true,
  source: "live" as const,
  traces: [
    makeTrace("t-real", "get_data", 10, 500, 2),
    {
      ...makeTrace("t-noise-1", "tools/list", 20, 1, 1),
      span_count: 1,
      spans: [makeTrace("t-noise-1", "tools/list", 20, 1, 1).spans[0]],
    },
    {
      ...makeTrace("t-noise-2", "initialize", 30, 2, 1),
      span_count: 1,
      spans: [makeTrace("t-noise-2", "initialize", 30, 2, 1).spans[0]],
    },
  ],
};

// ── Insights ────────────────────────────────────────────────

export const INSIGHTS_HAPPY = {
  success: true,
  analysis: {
    traceCount: 31,
    protocolTracesFiltered: 12,
    totalDurationMs: 45200,
    toolUsage: {
      shell: 90,
      get_result: 54,
      validate_sql: 26,
      get_data: 8,
      run_sql: 5,
    },
    errors: [],
    errorCount: 0,
    validationFailures: [],
    validationFailureCount: 0,
    costTiers: {},
    repeatedQueries: [
      {
        sql_preview: "SELECT count(*) FROM users",
        full_sql: "SELECT count(*) FROM users",
        count: 3,
        first_seen: NOW - 3600,
        last_seen: NOW - 600,
        is_example: false,
        example_id: null,
      },
      {
        sql_preview: "SELECT id, name FROM users WHERE active = true",
        full_sql: "SELECT id, name FROM users WHERE active = true",
        count: 2,
        first_seen: NOW - 7200,
        last_seen: NOW - 1800,
        is_example: true,
        example_id: "abc123",
      },
    ],
    tablesReferenced: {
      "dwh.public.cdrs": 15,
      "dwh.public.subs": 8,
      "dwh.public.cdr_agg_day": 5,
    },
    knowledgeEvents: [
      {
        tool: "query_approve",
        feedback_type: "approval",
        examples_added: 1,
        rules_added: null,
        timestamp: NOW - 1800,
      },
    ],
    knowledgeCaptureCount: 28,
    shellCommands: [],
    knowledgeStatus: {
      hasSchema: true,
      hasDomain: true,
      exampleCount: 30,
      ruleCount: 80,
    },
    insights: {
      generationCalls: 8,
      callsWithExamples: 6,
      callsWithRules: 8,
      callsWithoutExamples: 2,
      exampleHitRate: 0.75,
      validateCalls: 26,
      validateFailRate: 0,
      knowledgeCapturesByType: { approval: 20, feedback: 8 },
      sessionCount: 5,
    },
    vocabularyGaps: [
      {
        id: "gap-1",
        terms: [
          {
            term: "nas_id",
            searchCount: 4,
            session: "s1",
            timestamp: NOW - 3600,
          },
          {
            term: "nasid",
            searchCount: 2,
            session: "s2",
            timestamp: NOW - 3000,
          },
        ],
        totalSearches: 6,
        timestamp: NOW - 3600,
        schemaMatches: [
          {
            name: "nas_id",
            table: "dwh.public.cdrs.nas_id",
            type: "column" as const,
          },
        ],
        suggestedRule: "nas_ids, nas_id, nas_identifier, nasid are synonyms.",
        status: "open" as const,
        source: "traces" as const,
      },
      {
        id: "gap-2",
        terms: [
          { term: "cui", searchCount: 3, session: "s1", timestamp: NOW - 2400 },
        ],
        totalSearches: 3,
        timestamp: NOW - 2400,
        schemaMatches: [],
        suggestedRule: null,
        status: "open" as const,
        source: "traces" as const,
      },
      {
        id: "gap-3",
        terms: [
          {
            term: "greenfield",
            searchCount: 1,
            session: "s3",
            timestamp: NOW - 1200,
          },
        ],
        totalSearches: 1,
        timestamp: NOW - 1200,
        schemaMatches: [],
        suggestedRule: "greenfield hotspot and HMH are synonyms.",
        status: "resolved" as const,
        source: "traces" as const,
      },
    ],
  },
};

export const INSIGHTS_EMPTY = {
  success: true,
  analysis: {
    traceCount: 0,
    protocolTracesFiltered: 0,
    totalDurationMs: 0,
    toolUsage: {},
    errors: [],
    errorCount: 0,
    validationFailures: [],
    validationFailureCount: 0,
    costTiers: {},
    repeatedQueries: [],
    tablesReferenced: {},
    knowledgeEvents: [],
    knowledgeCaptureCount: 0,
    shellCommands: [],
    knowledgeStatus: {
      hasSchema: false,
      hasDomain: false,
      exampleCount: 0,
      ruleCount: 0,
    },
    insights: {
      generationCalls: 0,
      callsWithExamples: 0,
      callsWithRules: 0,
      callsWithoutExamples: 0,
      exampleHitRate: null,
      validateCalls: 0,
      validateFailRate: null,
      knowledgeCapturesByType: {},
      sessionCount: 0,
    },
    vocabularyGaps: [],
  },
};

export const INSIGHTS_ERROR = {
  success: false,
  error: "Failed to analyze traces: no traces found",
  analysis: null,
};

export const ADD_RULE_SUCCESS = {
  success: true,
};

export const ADD_RULE_DUPLICATE = {
  success: true,
  duplicate: true,
};

export const DISMISS_GAP_SUCCESS = {
  success: true,
  count: 1,
};

export const SAVE_EXAMPLE_SUCCESS = {
  success: true,
  example_id: "def456",
  total_examples: 32,
};

// ── Metrics & Dimensions ────────────────────────────────────

export const METRICS_LIST_HAPPY = {
  success: true,
  metrics: [
    {
      name: "daily_active_users",
      display_name: "Daily Active Users",
      description:
        "Count of unique users who logged in within the last 24 hours",
      sql: "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE created_at >= CURRENT_DATE",
      tables: ["sessions"],
      parameters: [],
      tags: ["engagement", "kpi"],
      dimensions: ["carrier", "city"],
      notes: "Excludes test accounts",
      created_at: "2025-01-15T10:00:00Z",
      created_by: "manual",
    },
    {
      name: "total_revenue",
      display_name: "Total Revenue",
      description: "Sum of all completed order totals",
      sql: "SELECT SUM(total) FROM orders WHERE status = 'completed'",
      tables: ["orders"],
      parameters: [],
      tags: ["revenue", "kpi"],
      dimensions: [],
      notes: null,
      created_at: "2025-01-10T08:00:00Z",
      created_by: "approved",
    },
  ],
  dimensions: [
    {
      name: "carrier",
      display_name: "Carrier",
      description: "Mobile network carrier",
      type: "categorical",
      column: "cdr_agg_day.carrier",
      tables: ["cdr_agg_day"],
      values: ["tmo", "helium_mobile", "att"],
      synonyms: ["network", "provider"],
      created_at: "2025-01-12T09:00:00Z",
      created_by: "approved",
    },
    {
      name: "report_date",
      display_name: "Report Date",
      description: "Date dimension for daily aggregations",
      type: "temporal",
      column: "cdr_agg_day.report_date",
      tables: ["cdr_agg_day"],
      values: [],
      synonyms: ["date", "day"],
      created_at: "2025-01-12T09:00:00Z",
      created_by: "manual",
    },
  ],
  metricCount: 2,
  dimensionCount: 2,
};

export const METRICS_LIST_EMPTY = {
  success: true,
  metrics: [],
  dimensions: [],
  metricCount: 0,
  dimensionCount: 0,
};

export const METRICS_ADD_SUCCESS = {
  success: true,
  name: "new_metric",
  type: "metric",
  filePath: "/home/user/.db-mcp/connections/production/metrics/catalog.yaml",
};

export const METRICS_ADD_DIMENSION_SUCCESS = {
  success: true,
  name: "new_dimension",
  type: "dimension",
  filePath: "/home/user/.db-mcp/connections/production/metrics/dimensions.yaml",
};

export const METRICS_UPDATE_SUCCESS = {
  success: true,
  name: "daily_active_users",
  type: "metric",
};

export const METRICS_DELETE_SUCCESS = {
  success: true,
  name: "daily_active_users",
  type: "metric",
};

export const METRICS_CANDIDATES_HAPPY = {
  success: true,
  metricCandidates: [
    {
      metric: {
        name: "count_sessions",
        display_name: "Count Sessions",
        description: "Count all sessions from the sessions table",
        sql: "SELECT COUNT(*) FROM sessions",
        tables: ["sessions"],
        tags: [],
        dimensions: [],
      },
      confidence: 0.7,
      source: "examples",
      evidence: ["example_001.yaml"],
    },
    {
      metric: {
        name: "avg_duration",
        display_name: "Avg Duration",
        description: "Average session duration",
        sql: "SELECT AVG(duration_ms) FROM sessions",
        tables: ["sessions"],
        tags: [],
        dimensions: [],
      },
      confidence: 0.5,
      source: "examples",
      evidence: ["example_003.yaml"],
    },
  ],
  dimensionCandidates: [
    {
      dimension: {
        name: "city",
        display_name: "City",
        description: "Dimension from GROUP BY in: sessions by city",
        type: "geographic",
        column: "sessions.city",
        tables: ["sessions"],
        values: [],
        synonyms: [],
      },
      confidence: 0.6,
      source: "examples",
      evidence: ["example_002.yaml"],
      category: "Location",
    },
  ],
};

export const METRICS_CANDIDATES_EMPTY = {
  success: true,
  metricCandidates: [],
  dimensionCandidates: [],
};

export const METRICS_APPROVE_SUCCESS = {
  success: true,
  name: "count_sessions",
  type: "metric",
};
