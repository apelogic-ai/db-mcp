# db-mcp UI Spec

**Status**: Draft  
**Created**: 2025-01-23  
**Updated**: 2025-01-23 (BICP integration)

## Overview

A local-first control plane, visualization layer, and **BICP client** for the db-mcp sidecar. The UI provides:

- Management of data connectors and semantic context
- Natural language querying with visualization
- Human-in-the-loop query approval
- Observability into query execution

The UI communicates with the sidecar using the **Business Intelligence Client Protocol (BICP)**, enabling rich analytics experiences beyond simple tool calls.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    db-mcp UI (Next.js)                        │
│                    ════════════════════                       │
│                    BICP Client Implementation                 │
│                                                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────┐ │
│  │ Connectors  │ │  Context    │ │   Query     │ │ Explorer│ │
│  │    Tab      │ │   Viewer    │ │   Console   │ │   Tab   │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ BICP (JSON-RPC over HTTP/WebSocket)
                            ▼
┌───────────────────────────────────────────────────────────────┐
│                 Python Sidecar (DBMCP)                        │
│                 ══════════════════════                        │
│                 BICP Agent + MCP Server                       │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                 BICP Agent Handler                       │ │
│  │  • initialize (capability negotiation)                   │ │
│  │  • schema/list, schema/describe                          │ │
│  │  • query/create, query/candidates, query/approve         │ │
│  │  • query/progress, query/result, query/complete          │ │
│  │  • query/refine, semantic/search                         │ │
│  │  • session/new, session/end                              │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                 MCP Server (existing)                    │ │
│  │  • Tools: validate_sql, run_sql, introspect, etc.       │ │
│  │  • For Claude Desktop integration                        │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                 Knowledge Vault                          │ │
│  │  • Schema descriptions   • Domain models                 │ │
│  │  • Metrics definitions   • Query examples                │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
    ┌────────────┐   ┌────────────┐   ┌────────────┐
    │  Claude    │   │ Databases  │   │    LLM     │
    │  Desktop   │   │ (PG, CH,   │   │   (Claude  │
    │  (MCP)     │   │  Trino)    │   │    API)    │
    └────────────┘   └────────────┘   └────────────┘
```

**Key architectural points:**

- **Dual protocol support**: Sidecar serves both MCP (for Claude Desktop) and BICP (for UI and future BI tools)
- **BICP handles query lifecycle**: Natural language → candidates → approval → execution → results
- **UI is a reference BICP client**: Demonstrates the protocol, works with any BICP-compatible agent
- **Static export**: Next.js builds to static files, served by Python sidecar
- **Single binary distribution**: PyInstaller bundles UI + sidecar

## Installation & Modes

User downloads a local executable and launches it.

On first run, user chooses mode:

| Mode | Description |
|------|-------------|
| **Team** | Pull configuration from a shared Git repository |
| **Individual** | Fully local, user-managed configuration |

## Application Structure

Five primary tabs:

| Tab | Purpose | BICP Messages Used |
|-----|---------|-------------------|
| **Data Connectors** | Manage data/API connections | `initialize` |
| **Context Viewer** | View/edit semantic layer | `schema/list`, `schema/describe`, `semantic/search` |
| **Query Console** | Natural language querying | `query/create`, `query/candidates`, `query/approve`, `query/refine` |
| **MCP Tools** | Control tool exposure | Configuration API (non-BICP) |
| **Query Explorer** | Observability | `query/progress`, `query/result`, `query/complete` |

---

## Tab 1: Data Connectors

Manages all data/API connections exposed through BICP and MCP.

### Connector Types

| Type | Inputs | Behavior |
|------|--------|----------|
| **Database** | Name, connection string | Primary data source for BICP queries |
| **File** | Name, file path(s) | csv-mcp for CSV/Parquet/Excel |
| **Generic API** | Tool name, endpoint, API key, description | MCP tool forwarding to endpoint |
| **BI Tool** | Dropdown (Superset, Metabase, Tableau) | Integration-specific MCP with predefined tools |
| **Transform** | dbt project path | dbt-mcp for running models |

### BICP Integration

When a connector is enabled, the BICP `initialize` response includes it in `dataSources`:

```json
{
  "dataSources": [
    {
      "id": "main_db",
      "name": "Analytics Warehouse",
      "type": "postgresql",
      "catalogs": ["public", "analytics"]
    },
    {
      "id": "sales_csv",
      "name": "Sales Data",
      "type": "csv",
      "catalogs": ["default"]
    }
  ]
}
```

### Connector Controls

- **Enable/disable toggle**: Controls BICP `dataSources` exposure
- **Test connection**: Triggers BICP `initialize` handshake
- **Status indicator**: Based on last `initialize` result
- **Onboarding status**: Discovery → Review → Domain Building → Complete

### UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Data Connectors                            [+ Add New ▼]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ● main_db                                [Toggle ON] │   │
│  │   PostgreSQL · localhost:5432/analytics              │   │
│  │   Status: Connected · Onboarding: Complete           │   │
│  │   [Test] [Configure] [Remove]                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ● sales_data                             [Toggle ON] │   │
│  │   CSV · ~/data/sales_2024.csv                        │   │
│  │   Status: Loaded · 1.2M rows                         │   │
│  │   [Test] [Configure] [Remove]                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ○ superset_prod                         [Toggle OFF] │   │
│  │   Superset · https://superset.company.com            │   │
│  │   Error: Authentication failed                       │   │
│  │   [Test] [Configure] [Remove]                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Tab 2: Context Viewer

Human-readable view of the semantic layer, powered by BICP schema discovery.

### BICP Integration

The Context Viewer uses these BICP messages:

| Action | BICP Message |
|--------|--------------|
| Load tree structure | `schema/list` with `schemaPattern` |
| Get table details | `schema/describe` with `includeSemantics: true` |
| Search metrics/dimensions | `semantic/search` |
| Browse metrics catalog | `semantic/search` with `types: ["metric"]` |

### Tree Hierarchy

```
📁 Nova (user-created folder)
├── 📊 main_db (database)
│   ├── 📁 public (schema)
│   │   ├── 📋 users
│   │   │   ├── 📏 daily_active_users (metric)
│   │   │   └── 📏 user_retention (metric)
│   │   ├── 📋 orders
│   │   └── 📋 products
│   └── 📁 analytics (schema)
│       └── 📋 daily_metrics
├── 📄 sales_data.csv (file)
└── 🔌 superset_prod (BI tool)

📁 Uncategorized
└── 📊 staging_db
```

### Node Selection → BICP Response

When a table is selected, the UI calls `schema/describe` and displays:

```
┌────────────────────────────────────────────────────────────┐
│  Table: public.users                                       │
│  ──────────────────────────────────────────────────────── │
│                                                            │
│  Description:                                              │
│  User interaction events from web and mobile applications. │
│  Each row represents a single event such as a page view,   │
│  button click, or purchase.                                │
│                                                            │
│  Row Count Estimate: ~1.25B rows                           │
│                                                            │
│  Columns:                                                  │
│  ┌────────────────┬───────────┬────────────────────────┐  │
│  │ Name           │ Type      │ Semantics              │  │
│  ├────────────────┼───────────┼────────────────────────┤  │
│  │ event_timestamp│ TIMESTAMP │ timestamp (UTC)        │  │
│  │ user_id        │ VARCHAR   │ FK → users.user_id     │  │
│  │ event_type     │ VARCHAR   │ category: pageview,    │  │
│  │                │           │ click, purchase, signup│  │
│  └────────────────┴───────────┴────────────────────────┘  │
│                                                            │
│  Relationships:                                            │
│  • user_id → users.user_id (many-to-one)                  │
│                                                            │
│  Defined Metrics:                                          │
│  • daily_active_users: COUNT(DISTINCT user_id)            │
│    "Unique users with at least one event per day"         │
│                                                            │
│  [Edit Descriptions] [Add Metric]                          │
└────────────────────────────────────────────────────────────┘
```

### Semantic Search

A search bar at the top uses `semantic/search`:

```
┌─────────────────────────────────────────────────────────────┐
│  🔍 Search metrics and dimensions...    [revenue]          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Results for "revenue":                                     │
│                                                             │
│  📏 total_revenue (metric)                                  │
│     SUM(transactions.amount_usd)                           │
│     Tables: transactions · Tags: finance, kpi              │
│                                                             │
│  📏 arpu (metric)                                           │
│     Average revenue per user                               │
│     Tables: transactions · Tags: finance, per-user         │
│                                                             │
│  📐 revenue_tier (dimension)                                │
│     Customer segmentation by lifetime value                │
│     Tables: users · Tags: segmentation                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Tab 3: Query Console (NEW)

Natural language querying interface — the primary BICP client experience.

### BICP Query Lifecycle

```
User Input                    BICP Messages
──────────────────────────────────────────────────────────
"Show DAU by platform"   →   query/create
                         ←   query/candidates (2-3 options)
User approves candidate  →   query/approve
                         ←   query/progress (streaming)
                         ←   query/result (streaming)
                         ←   query/complete (with insights)
"Filter to just mobile"  →   query/refine
                         ←   query/candidates (refined)
```

### UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Query Console                          Session: sess_abc1 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Show me daily active users for the last 30 days     │   │
│  │ by platform                                    [Ask] │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ═══════════════════════════════════════════════════════   │
│                                                             │
│  Query Candidates (awaiting approval)                      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ○ Candidate 1                        Confidence: 92% │   │
│  │                                                       │   │
│  │ SELECT                                                │   │
│  │   DATE_TRUNC('day', event_timestamp) AS day,         │   │
│  │   platform,                                          │   │
│  │   COUNT(DISTINCT user_id) AS dau                     │   │
│  │ FROM events                                          │   │
│  │ WHERE event_timestamp >= CURRENT_DATE - INTERVAL '30'│   │
│  │ GROUP BY 1, 2                                        │   │
│  │ ORDER BY 1                                           │   │
│  │                                                       │   │
│  │ Explanation: Counts unique users per day, grouped    │   │
│  │ by platform (iOS/Android/Web), for the last 30 days. │   │
│  │                                                       │   │
│  │ Cost: ~125MB scan · 2-5 seconds · Low                │   │
│  │ Visualization: Line Chart recommended                │   │
│  │                                                       │   │
│  │ [Approve] [Edit SQL] [Reject]                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ○ Candidate 2                        Confidence: 87% │   │
│  │   Alternative using CTE for clarity...               │   │
│  │ [Expand] [Approve]                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### After Approval: Results with Visualization

```
┌─────────────────────────────────────────────────────────────┐
│  Query Console                          Session: sess_abc1 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Now filter to just iOS and Android           [Ask]  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Previous: "Show me daily active users for the last 30..." │
│                                                             │
│  ═══════════════════════════════════════════════════════   │
│                                                             │
│  Results (90 rows · 4.8s · 125MB scanned)                  │
│                                                             │
│  [Chart] [Table] [SQL] [Export ▼]                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         DAU by Platform (Last 30 Days)              │   │
│  │                                                       │   │
│  │  250K ┤                                    ▄▄▄       │   │
│  │       │                              ▄▄▄▄▄███       │   │
│  │  200K ┤                        ▄▄▄▄▄█████████  Web  │   │
│  │       │                  ▄▄▄▄▄███████████████       │   │
│  │  150K ┤            ▄▄▄▄██████████████████████       │   │
│  │       │      ▄▄▄▄▄███████████████████████████  iOS  │   │
│  │  100K ┤▄▄▄▄▄█████████████████████████████████       │   │
│  │       │██████████████████████████████████████Android│   │
│  │   50K ┤██████████████████████████████████████       │   │
│  │       └──────────────────────────────────────       │   │
│  │        Dec 24        Jan 1         Jan 15           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Insights:                                                  │
│  • iOS DAU grew 12% week-over-week                         │
│  • Web remains dominant at 48% of total DAU                │
│  • Christmas Day showed a 7% dip across all platforms      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Query Refinement

When user types a follow-up, the UI sends `query/refine` with `previousQueryId`:

```json
{
  "method": "query/refine",
  "params": {
    "sessionId": "sess_abc1",
    "previousQueryId": "qry_xyz789",
    "refinement": {
      "type": "natural_language",
      "text": "Now filter to just iOS and Android"
    }
  }
}
```

---

## Tab 4: MCP Tools

Controls which MCP tools Claude Desktop can access. This tab uses configuration APIs (not BICP).

### Layout

**Left pane**: Tree structure grouped by connection

**Right pane**: Tool list and controls for selected connection

### Tool Information

For each tool:
- Name and description
- Invocation frequency (from Query Explorer data)
- Enable/disable toggle

### UI Layout

```
┌────────────────────────┬────────────────────────────────────┐
│  MCP Tools             │  main_db Tools                     │
├────────────────────────┤                                    │
│                        │  Available:                        │
│  📊 main_db            │  ┌────────────────────────────────┐│
│  📄 sales.csv          │  │ ☑ execute_sql                  ││
│  🔌 superset           │  │   Execute SQL queries          ││
│                        │  │   Used: 145 times              ││
│  ──────────────────    │  ├────────────────────────────────┤│
│  Global Exposed:       │  │ ☑ introspect_schema            ││
│  • execute_sql         │  │   Get table/column metadata    ││
│  • introspect_schema   │  │   Used: 23 times               ││
│  • generate_sql        │  ├────────────────────────────────┤│
│  • load_csv            │  │ ☐ dangerous_operation          ││
│                        │  │   Drop tables (disabled)       ││
│                        │  │   Used: 0 times                ││
│                        │  └────────────────────────────────┘│
│                        │                                    │
│                        │  [Save Changes]                    │
└────────────────────────┴────────────────────────────────────┘
```

---

## Tab 5: Query Explorer (Observability)

Visibility into BICP query execution and MCP tool usage.

### BICP Integration

Query Explorer visualizes BICP query lifecycle:

| Query State | Visualization |
|-------------|---------------|
| `drafting` | Spinner, "Generating candidates..." |
| `awaiting_approval` | Candidate cards with approve/reject |
| `executing` | Progress bar from `query/progress` |
| `streaming` | Live result table population |
| `complete` | Full results with insights |
| `failed` | Error details with diagnostics |

### Timeline View

```
┌─────────────────────────────────────────────────────────────┐
│  Query Explorer                    [Filter ▼] [Time Range] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Timeline                                                   │
│  ──────────────────────────────────────────────────────────│
│                                                             │
│  10:23:45  "Show revenue by region"              [BICP]    │
│            ├── query/create                                │
│            ├── query/candidates (2 options, 45ms)          │
│            ├── query/approve (candidate_1)                 │
│            ├── query/progress (0% → 100%, 4.2s)           │
│            ├── query/result (90 rows)                      │
│            └── query/complete ✓                            │
│                Insights: "Q4 revenue up 23%..."            │
│                                                             │
│  10:22:31  "What tables have customer data?"     [BICP]    │
│            ├── schema/list                                 │
│            └── schema/describe (3 tables) ✓                │
│                                                             │
│  10:21:15  introspect_schema                     [MCP]     │
│            └── tool call from Claude Desktop (89ms) ✓      │
│                                                             │
│  10:20:02  "Calculate DAU for last week"         [BICP]    │
│            ├── query/create                                │
│            ├── query/candidates (1 option)                 │
│            ├── query/approve                               │
│            └── query/progress ✗ timeout after 30s          │
│                                                             │
│  ──────────────────────────────────────────────────────────│
│  Selected: query @ 10:23:45                                │
│                                                             │
│  SQL Executed:                                              │
│  SELECT region, SUM(amount) as revenue                     │
│  FROM orders WHERE date >= '2025-01-01'                    │
│  GROUP BY region ORDER BY revenue DESC                     │
│                                                             │
│  Cost: 125MB scanned · 4.2s execution                      │
│  Result: 8 rows                                            │
│                                                             │
│  [View Results] [Copy SQL] [Re-run]                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Onboarding Flow

For new database connections, the UI guides users through onboarding phases:

| Phase | UI Experience | BICP Usage |
|-------|---------------|------------|
| **Discovery** | Progress bar, live table/column counts | `schema/list` polling |
| **Review** | Table list with description fields, ignore patterns | `schema/describe` for each table |
| **Domain Building** | Preview generated domain model | Agent-side LLM call |
| **Complete** | Summary, ready for queries | Full BICP capability |

The Context Viewer tab doubles as the onboarding UI with wizard overlays for new sources.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **UI Framework** | Next.js 14+ (App Router) with static export |
| **Styling** | Tailwind CSS |
| **Components** | shadcn/ui |
| **State Management** | Zustand (local) + React Query (server state) |
| **BICP Client** | Custom JSON-RPC client over HTTP/WebSocket |
| **Tree View** | react-arborist |
| **Code Editor** | Monaco (for SQL editing) |
| **Charts** | Recharts or Nivo |
| **Tables** | TanStack Table |
| **Backend** | FastAPI (Python sidecar) |
| **Distribution** | PyInstaller binary with bundled static files |

---

## Project Structure

```
db-mcp/
├── packages/
│   ├── core/                    # Python sidecar
│   │   ├── src/db_mcp/
│   │   │   ├── bicp/            # NEW: BICP agent implementation
│   │   │   │   ├── __init__.py
│   │   │   │   ├── handler.py   # JSON-RPC message routing
│   │   │   │   ├── session.py   # Session management
│   │   │   │   ├── query.py     # Query lifecycle
│   │   │   │   └── schema.py    # Schema discovery
│   │   │   ├── server.py        # MCP server (existing)
│   │   │   └── ui_server.py     # FastAPI: serves UI + BICP endpoint
│   │   └── static/              # Next.js build output
│   │
│   ├── models/                  # Shared Pydantic models
│   │   └── src/db_mcp_models/
│   │       ├── bicp.py          # NEW: BICP message types
│   │       └── ...
│   │
│   └── ui/                      # Next.js project
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   ├── connectors/
│       │   │   └── page.tsx
│       │   ├── context/
│       │   │   └── page.tsx
│       │   ├── query/           # NEW: Query Console
│       │   │   └── page.tsx
│       │   ├── tools/
│       │   │   └── page.tsx
│       │   └── explorer/
│       │       └── page.tsx
│       ├── components/
│       │   ├── ui/              # shadcn components
│       │   ├── bicp/            # NEW: BICP-specific components
│       │   │   ├── query-input.tsx
│       │   │   ├── candidate-card.tsx
│       │   │   ├── result-table.tsx
│       │   │   ├── result-chart.tsx
│       │   │   └── progress-bar.tsx
│       │   ├── tree-view.tsx
│       │   ├── connector-card.tsx
│       │   └── trace-timeline.tsx
│       ├── lib/
│       │   ├── bicp-client.ts   # NEW: BICP JSON-RPC client
│       │   ├── api.ts
│       │   └── hooks.ts
│       ├── next.config.js
│       ├── package.json
│       └── tailwind.config.js
```

---

## BICP Client Implementation

### TypeScript Client

```typescript
// lib/bicp-client.ts

interface BICPClient {
  // Initialization
  initialize(): Promise<InitializeResult>;
  
  // Schema Discovery
  listSchemas(dataSourceId: string, catalog?: string): Promise<Schema[]>;
  describeTable(table: string, options?: DescribeOptions): Promise<TableDescription>;
  
  // Queries
  createQuery(input: QueryInput, options?: QueryOptions): Promise<string>; // returns queryId
  approveQuery(queryId: string, candidateId: string): Promise<void>;
  rejectQuery(queryId: string, reason: string): Promise<void>;
  refineQuery(previousQueryId: string, refinement: string): Promise<string>;
  
  // Semantic Layer
  searchSemantics(query: string, types?: SemanticType[]): Promise<SemanticItem[]>;
  
  // Sessions
  createSession(): Promise<string>; // returns sessionId
  endSession(sessionId: string): Promise<void>;
  
  // Event Streams
  onCandidates(callback: (candidates: QueryCandidate[]) => void): void;
  onProgress(callback: (progress: QueryProgress) => void): void;
  onResult(callback: (result: QueryResult) => void): void;
  onComplete(callback: (summary: QuerySummary) => void): void;
}
```

### WebSocket Connection

For streaming updates (`query/progress`, `query/result`), the client maintains a WebSocket connection:

```typescript
// Notifications from agent
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.method) {
    case 'query/candidates':
      setCandidates(message.params.candidates);
      break;
    case 'query/progress':
      setProgress(message.params.progress);
      break;
    case 'query/result':
      appendResults(message.params.result);
      break;
    case 'query/complete':
      setInsights(message.params.insights);
      break;
  }
};
```

---

## Development Workflow

### Local Development

```bash
# Terminal 1: Python sidecar with BICP endpoint
cd packages/core
uv run uvicorn db_mcp.ui_server:app --reload --port 8080

# Terminal 2: Next.js dev server
cd packages/ui
npm run dev  # localhost:3000, proxies to :8080
```

### Production Build

```bash
# Build UI static files
cd packages/ui
npm run build  # outputs to ../core/static/

# Build binary (includes static files)
cd packages/core
uv run python scripts/build.py
```

### CLI Integration

```bash
db-mcp ui              # Start UI server, open browser
db-mcp ui --port 9000  # Custom port
```

---

## API Endpoints

### BICP Endpoint (Primary)

```
POST /bicp              # JSON-RPC endpoint for all BICP messages
WS   /bicp/stream       # WebSocket for notifications
```

### Configuration API (Non-BICP)

```
GET    /api/connectors           # List all connectors
POST   /api/connectors           # Create connector
PUT    /api/connectors/:id       # Update connector
DELETE /api/connectors/:id       # Remove connector

GET    /api/tools                # List MCP tools
PUT    /api/tools/exposed        # Update exposed tools

GET    /api/config               # Get global configuration
PUT    /api/config               # Update configuration
```

---

## Visualization Rendering

The UI interprets BICP visualization hints from `query/candidates` and `query/result`:

| BICP `recommended` | UI Component |
|--------------------|--------------|
| `table` | TanStack Table with sorting, filtering, pagination |
| `line_chart` | Recharts LineChart |
| `bar_chart` | Recharts BarChart |
| `stacked_bar` | Recharts BarChart with stacking |
| `pie_chart` | Recharts PieChart |
| `single_value` | Large KPI display card |
| `pivot_table` | TanStack Table with grouping |

Graceful degradation: If `recommended` type isn't supported, check `alternatives`, fall back to `table`.

---

## Open Questions

1. **Electron timeline**: Start with local web, add Electron shell in v1?

2. **BICP transport**: HTTP+WebSocket vs pure WebSocket?

3. **Component library**: shadcn/ui confirmed?

4. **Chart library**: Recharts vs Nivo vs ECharts?

5. **Onboarding priority**: Part of v0 or fast-follow?

6. **Query history persistence**: Local storage vs sidecar DB?

---

## Relationship to Other Docs

| Document | Relationship |
|----------|--------------|
| [`../bicp/spec/bicp-v0.1.md`](../../bicp/spec/bicp-v0.1.md) | BICP protocol specification (separate repo) |
| `data-gateway.md` | UI is the control plane for the gateway architecture |
| `electron-port-feasibility.md` | Confirms sidecar pattern; Electron is optional wrapper |
| `metrics-layer.md` | Metrics surface via `semantic/search` in Context Viewer |
| `knowledge-extraction-agent.md` | Learnings surface in Query Explorer insights |

## Dependencies

The UI depends on packages from the BICP repo (`../bicp/`):

| Package | Location | Usage |
|---------|----------|-------|
| `bicp-client` | `../bicp/packages/client-typescript` | TypeScript client for BICP protocol |
| `bicp-agent` | `../bicp/packages/agent-python` | Python agent framework (used by sidecar) |

These are linked as local dependencies during development. See `packages/ui/package.json` and `packages/core/pyproject.toml`.
