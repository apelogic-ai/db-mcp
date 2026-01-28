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
