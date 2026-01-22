# DB-MCP Electron/TypeScript Port Feasibility

**Status**: Planning  
**Created**: 2026-01-21  
**Decision**: Electron shell + db-mcp sidecar binary

## Executive Summary

This document analyzes packaging DB-MCP as a desktop application. After evaluating full TypeScript rewrite vs hybrid approaches, **we've decided on Electron shell + bundled db-mcp binary (sidecar pattern)**.

This is a proven architecture (VS Code + language servers, Cursor + various backends) that:
- Preserves existing Python codebase investment
- Ships faster (4-6 weeks vs 12-14 weeks for full rewrite)
- Avoids SQLAlchemy introspection rewrite (biggest risk)
- Still delivers native desktop experience

---

# Appendix: Analysis & Background

The sections below document the analysis that led to the sidecar decision.

---

## Current Python Codebase

### Codebase Stats

| Component | Lines | Purpose |
|-----------|-------|---------|
| `db/introspection.py` | 393 | Schema discovery via SQLAlchemy |
| `validation/explain.py` | 538 | SQL validation, EXPLAIN parsing |
| `vault/migrate.py` | 423 | Storage format migration |
| `vault/init.py` | 355 | Vault initialization |
| `onboarding/ignore.py` | 325 | Schema filtering rules |
| `onboarding/schema_store.py` | 285 | Schema description persistence |
| `onboarding/state.py` | 240 | Onboarding state machine |
| `console/ui.py` | 435 | Terminal UI (Rich) |
| `console/instrument.py` | 277 | OpenTelemetry instrumentation |
| `traces.py` | 162 | Trace management |
| Other modules | ~8,500 | CLI, config, tools, MCP server |
| **Total** | ~12,000 | |

### Key Dependencies

| Python Package | Purpose | Criticality |
|----------------|---------|-------------|
| `sqlalchemy` | DB introspection, connection pooling | **Critical** |
| `trino` | Trino driver + auth | **Critical** |
| `clickhouse-sqlalchemy` | ClickHouse dialect | **Critical** |
| `psycopg2-binary` | PostgreSQL driver | **Critical** |
| `pymysql` | MySQL driver | Medium |
| `pymssql` | SQL Server driver | Medium |
| `fastmcp` | MCP server framework | **Critical** |
| `pydantic-ai` | LLM integration | Medium |
| `sqlglot` | SQL parsing/transpilation | High |
| `opentelemetry-*` | Tracing | Low |
| `rich` | Terminal UI | Low (N/A for Electron) |
| `pyyaml` | Config files | Low |

---

## TypeScript Equivalents Analysis

### Database Connectivity

| Python | TypeScript Equivalent | Gap Assessment |
|--------|----------------------|----------------|
| SQLAlchemy (core) | `knex.js`, `kysely`, `drizzle-orm` | **Partial** - No equivalent introspection API |
| SQLAlchemy Inspector | None | **Major Gap** - Must build custom per-dialect |
| `trino` driver | `trino-client` (npm) | **Good** - Official client exists |
| `clickhouse-sqlalchemy` | `@clickhouse/client` | **Good** - Official client |
| `psycopg2` | `pg` (node-postgres) | **Good** - Mature |
| `pymysql` | `mysql2` | **Good** - Mature |
| `pymssql` | `tedious` / `mssql` | **Good** - Mature |

**Verdict**: Drivers exist, but **SQLAlchemy Inspector has no equivalent**. This is the biggest gap.

### Schema Introspection Challenge

SQLAlchemy's `inspect()` provides:
- `get_schema_names()` 
- `get_table_names(schema)`
- `get_columns(table, schema)` with types, nullability, defaults
- `get_pk_constraint(table)`
- `get_foreign_keys(table)`
- `get_indexes(table)`

In TypeScript, we'd need to write **dialect-specific introspection**:

```
PostgreSQL  → information_schema + pg_catalog queries
ClickHouse  → system.tables, system.columns
Trino       → SHOW CATALOGS/SCHEMAS/TABLES, DESCRIBE
MySQL       → information_schema
SQL Server  → sys.tables, sys.columns, INFORMATION_SCHEMA
```

**Effort**: ~500-800 lines per dialect (5 dialects = 2,500-4,000 lines)

### SQL Validation

| Python | TypeScript Equivalent | Gap Assessment |
|--------|----------------------|----------------|
| `sqlglot` | `node-sql-parser`, `pgsql-ast-parser` | **Partial** - Less dialect coverage |
| EXPLAIN parsing | Custom per-dialect | Same effort in both languages |

`sqlglot` supports 20+ dialects with transpilation. TypeScript parsers are more limited:
- `node-sql-parser`: MySQL, PostgreSQL, Trino, some others
- No unified transpilation layer

**Verdict**: Acceptable for validation, but lose transpilation capability.

### MCP Server

| Python | TypeScript Equivalent | Gap Assessment |
|--------|----------------------|----------------|
| `fastmcp` | `@modelcontextprotocol/sdk` | **Good** - Official SDK |

The official MCP TypeScript SDK is mature and well-documented. This is actually a **better fit** for Electron since Claude Desktop uses the TS SDK internally.

### LLM Integration

| Python | TypeScript Equivalent | Gap Assessment |
|--------|----------------------|----------------|
| `pydantic-ai` | `ai` (Vercel AI SDK), `langchain.js` | **Good** - Multiple options |

TypeScript has excellent LLM tooling. No gap here.

### File/Config Management

| Python | TypeScript Equivalent | Gap Assessment |
|--------|----------------------|----------------|
| `pyyaml` | `js-yaml` | **Good** |
| `pathlib` | `path`, `fs` | **Good** |
| Pydantic Settings | `zod`, `env-var` | **Good** |

No issues.

---

## Major Caveats and Blockers

### 1. Schema Introspection (BLOCKER)

**Problem**: No TypeScript equivalent to SQLAlchemy Inspector.

**Options**:
1. **Write custom introspection per dialect** (~3-4 weeks)
   - PostgreSQL: Query `information_schema` + `pg_catalog`
   - ClickHouse: Query `system.tables`, `system.columns`
   - Trino: Parse `SHOW` and `DESCRIBE` output
   - MySQL: Query `information_schema`
   - SQL Server: Query `sys.*` views

2. **Use database-specific ORMs** (complexity explosion)
   - Different APIs, different behaviors
   - Maintenance nightmare

3. **Embed Python introspection as subprocess** (hybrid approach)
   - Bundle `pyinstaller` binary for introspection only
   - Call via IPC from Electron
   - Defeats "pure TypeScript" goal but pragmatic

**Recommendation**: Option 1 (custom introspection) is cleanest but significant effort. Option 3 is faster but adds complexity.

### 2. Native Database Drivers

**Problem**: Some Node.js drivers require native compilation (libpq, tedious).

**Electron Considerations**:
- `pg` (PostgreSQL): Pure JS, no issues
- `mysql2`: Pure JS, no issues  
- `@clickhouse/client`: Pure JS (HTTP), no issues
- `trino-client`: Pure JS (HTTP), no issues
- `tedious` (SQL Server): Pure JS, no issues
- `better-sqlite3`: **Native module** - needs rebuild for Electron

**Verdict**: Most drivers are pure JS over HTTP. Native modules manageable via `electron-rebuild`.

### 3. MCP Transport in Electron

**Problem**: MCP typically uses stdio transport. In Electron:
- Main process can spawn MCP servers (works)
- Renderer process cannot directly access stdio
- Need IPC bridge between renderer and main process MCP client

**Solution**: Standard Electron IPC pattern. Not a blocker, just architecture work.

### 4. Bundling and Distribution

**Considerations**:
- Electron apps are large (~150MB base)
- Code signing required for macOS distribution
- Auto-update infrastructure needed
- Platform-specific builds (macOS, Windows, Linux)

**Tools**: `electron-builder`, `electron-forge` handle this well.

### 5. Security Model Changes

**Python (current)**:
- Runs as local process with user permissions
- Database credentials in `.env` or config files

**Electron**:
- Same security model, but...
- Credentials should use OS keychain (`keytar` package)
- Main process handles sensitive operations
- Renderer process is sandboxed

**Effort**: Medium - need to add keychain integration.

---

## Component-by-Component Port Analysis

### Easy to Port (Low Risk)

| Component | Effort | Notes |
|-----------|--------|-------|
| Config management | 1 day | Pydantic → Zod |
| YAML file handling | 1 day | Direct equivalent |
| Vault/storage layer | 3 days | File operations, straightforward |
| MCP server | 3 days | Official TS SDK available |
| CLI → Electron UI | 5 days | Replace Rich TUI with React |
| OpenTelemetry | 2 days | `@opentelemetry/sdk-node` |

### Medium Effort (Some Risk)

| Component | Effort | Notes |
|-----------|--------|-------|
| SQL validation | 5 days | EXPLAIN parsing is dialect-specific |
| LLM integration | 3 days | Good TS options exist |
| Onboarding state machine | 3 days | Logic port, straightforward |

### Hard to Port (High Risk)

| Component | Effort | Notes |
|-----------|--------|-------|
| Schema introspection | 15-20 days | **No equivalent library** |
| Multi-dialect support | 10 days | Custom code per dialect |
| Connection pooling | 3 days | Less sophisticated than SQLAlchemy |

---

## Effort Estimate

### Full TypeScript Rewrite

| Phase | Effort | 
|-------|--------|
| Core infrastructure (config, storage, MCP) | 2 weeks |
| Database connectivity + drivers | 1 week |
| Schema introspection (all dialects) | 3-4 weeks |
| SQL validation layer | 1 week |
| Onboarding/domain tools | 1 week |
| Electron shell + UI | 2 weeks |
| Testing + polish | 2 weeks |
| **Total** | **12-14 weeks** |

### Hybrid Approach (Python introspection sidecar)

| Phase | Effort |
|-------|--------|
| TypeScript MCP server + tools | 3 weeks |
| Python introspection binary (pyinstaller) | 1 week |
| IPC bridge | 1 week |
| Electron shell + UI | 2 weeks |
| Testing + polish | 2 weeks |
| **Total** | **9-10 weeks** |

---

## Challenging the Monolith: Multiple Deployment Targets

The assumption that we need a single monolithic architecture is flawed. Users have different needs:

| User Type | Wants | Doesn't Want |
|-----------|-------|--------------|
| Developer with Python | CLI, `pip install`, integrates with existing tools | Heavy desktop app |
| Developer without Python | Single binary, no runtime deps | Installing Python/uv |
| Analyst | GUI, visual query builder | Terminal |
| Claude Desktop user | MCP server "just works" | Setup complexity |

**Key insight**: The MCP server is the core. Everything else is a **delivery mechanism**.

### Modular Architecture (Recommended)

Instead of one monolith, split into layers:

```
┌─────────────────────────────────────────────────────────┐
│                    Delivery Layer                        │
├─────────────┬─────────────┬─────────────┬───────────────┤
│  CLI (TS)   │  Electron   │  Web UI     │  VS Code Ext  │
│  `npx`      │  Desktop    │  (future)   │  (future)     │
└──────┬──────┴──────┬──────┴──────┬──────┴───────┬───────┘
       │             │             │              │
       └─────────────┴──────┬──────┴──────────────┘
                            │
┌───────────────────────────┴───────────────────────────┐
│                 MCP Server Core (TS)                   │
│  - Tools: introspect, query, validate, describe        │
│  - Resources: schema, examples, domain model           │
│  - Prompts: onboarding, query generation               │
└───────────────────────────┬───────────────────────────┘
                            │
┌───────────────────────────┴───────────────────────────┐
│              Database Adapter Layer (TS)               │
│  - PostgreSQL, ClickHouse, Trino, MySQL, MSSQL        │
│  - Custom introspection per dialect                    │
│  - Connection management                               │
└───────────────────────────────────────────────────────┘
```

### Delivery Options

**1. CLI via npx (zero install)**
```bash
npx @db-mcp/cli serve --connection postgres://...
npx @db-mcp/cli onboard
```
- Ships as npm package
- Works anywhere Node.js exists
- Same code as MCP server
- No Electron overhead

**2. Standalone Binary (no runtime)**
```bash
# Download single binary
curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh
db-mcp serve
```
- Bundle with `pkg` or `bun build --compile`
- ~50MB binary (vs 150MB Electron)
- Perfect for servers, CI/CD, Docker

**3. Electron Desktop (GUI users)**
- Full visual interface
- Connection wizard
- Query results grid
- For analysts who want GUI

**4. Claude Desktop Config (MCP users)**
```json
{
  "mcpServers": {
    "db-mcp": {
      "command": "npx",
      "args": ["@db-mcp/cli", "serve"]
    }
  }
}
```
- Leverages npx delivery
- No separate install needed
- Auto-updates via npm

### Why This is Better

| Concern | Monolith Electron | Modular Approach |
|---------|-------------------|------------------|
| CLI-only users | Forced to download 150MB GUI | `npx` or 50MB binary |
| GUI users | Get what they want | Electron optional |
| Bundle size | 150MB minimum | 5MB (npx) to 50MB (binary) |
| Update mechanism | Custom auto-updater | npm for CLI, standard for Electron |
| Development | One codebase, one target | One core, multiple thin shells |
| Testing | E2E requires Electron | Core testable independently |

### Code Sharing Strategy

```
packages/
├── @db-mcp/core/                   # MCP server, tools, adapters
│   ├── src/
│   │   ├── mcp/                    # MCP server implementation
│   │   ├── adapters/               # Database adapters
│   │   ├── introspection/          # Schema discovery
│   │   └── tools/                  # MCP tools
│   └── package.json
│
├── @db-mcp/cli/                    # CLI wrapper
│   ├── src/cli.ts                  # Commander/yargs CLI
│   └── package.json                # depends on core
│
└── @db-mcp/desktop/                # Electron app
    ├── src/
    │   ├── main/                   # Electron main process
    │   └── renderer/               # React UI
    └── package.json                # depends on core
```

---

## Alternative Architectures (Original Analysis)

### Option A: Pure TypeScript Monolith

```
Electron App
├── Main Process
│   ├── MCP Server (TS SDK)
│   ├── DB Connections (native drivers)
│   ├── Schema Introspector (custom per-dialect)
│   └── Query Validator
└── Renderer Process
    └── React UI
```

**Pros**: Single language, simpler deployment, no Python dependency  
**Cons**: Forces GUI on CLI users, large bundle always

### Option B: Hybrid (Python Sidecar)

```
Electron App
├── Main Process
│   ├── MCP Server (TS SDK)
│   ├── Python Sidecar (pyinstaller binary)
│   │   └── SQLAlchemy introspection
│   └── IPC Bridge
└── Renderer Process
    └── React UI
```

**Pros**: Leverages existing Python code, faster to ship  
**Cons**: Larger bundle, two runtimes, complexity

### Option C: Tauri Instead of Electron

```
Tauri App (Rust core)
├── Rust Backend
│   ├── MCP Server (Rust SDK exists)
│   ├── sqlx for DB connections
│   └── Custom introspection
└── Web Frontend
    └── React UI
```

**Pros**: Much smaller bundle (~10MB vs 150MB), better performance  
**Cons**: Rust learning curve, even less introspection tooling than TS

### Option D: Keep Python, Package with PyInstaller

```
Packaged Python App
├── PyInstaller bundle
│   └── Full DB-MCP
└── Electron Shell (optional, for UI only)
```

**Pros**: Minimal code changes, fastest path  
**Cons**: Large bundle, Python startup time, not "native" feel

---

## Decision: Electron Shell + db-mcp Sidecar

**Chosen approach**: Electron desktop app with bundled Python db-mcp binary.

### Why This Approach

| Factor | Full TS Rewrite | Sidecar (Chosen) |
|--------|-----------------|------------------|
| Timeline | 12-14 weeks | 4-6 weeks |
| Risk | High (introspection gap) | Low (proven pattern) |
| Python investment | Lost | Preserved |
| Bundle size | ~150MB | ~200MB (Electron + Python) |
| Maintenance | One codebase | Two codebases, clear boundary |

The sidecar pattern is battle-tested:
- **VS Code** bundles language servers
- **Cursor** bundles AI backends  
- **GitHub Desktop** bundles Git binary
- **Hyper** bundles shell

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                    Electron App                         │
├────────────────────────────────────────────────────────┤
│  Main Process (Node.js)                                │
│  ├── Window management                                 │
│  ├── Sidecar lifecycle (spawn/kill db-mcp)            │
│  ├── IPC bridge to renderer                           │
│  ├── Deep link handler (db-mcp://)                    │
│  └── Auto-updater                                      │
├────────────────────────────────────────────────────────┤
│  Renderer Process (React)                              │
│  ├── Connection manager UI                            │
│  ├── Query results grid (MUI X Data Grid)             │
│  ├── Schema browser                                    │
│  └── Onboarding wizard                                │
├────────────────────────────────────────────────────────┤
│  Bundled Resources                                     │
│  └── bin/                                              │
│      ├── db-mcp-darwin-arm64                          │
│      ├── db-mcp-darwin-x64                            │
│      ├── db-mcp-linux-x64                             │
│      └── db-mcp-win-x64.exe                           │
└────────────────────────────────────────────────────────┘
                          │
                          │ HTTP (localhost:8384)
                          │ or stdio (MCP)
                          ▼
┌────────────────────────────────────────────────────────┐
│                 db-mcp binary (Python)                 │
│  ├── MCP server (fastmcp)                             │
│  ├── Database introspection (SQLAlchemy)              │
│  ├── Query validation (EXPLAIN)                       │
│  ├── Console server (HTTP API)                        │
│  └── Connection vault (~/.db-mcp/connections/)        │
└────────────────────────────────────────────────────────┘
```

### What Already Exists

**db-mcp binary is already shipping:**
- PyInstaller spec file (`db-mcp.spec`) with all hidden imports configured
- Build script (`scripts/build.py`) producing ~67MB binary
- Install script (`scripts/install.sh`) with `curl | sh` support
- Release script (`scripts/release.sh`) for version bumping
- CI/CD workflow (`.github/workflows/release.yml`) building for:
  - macOS ARM64, macOS x64, Linux x64, Windows x64
- GitHub Releases with auto-generated release notes

**Console server exists (port 8384):**
- HTTP server for OTel traces (`console/server.py`)
- Endpoints: `/`, `/api/traces`, `/api/spans`, `/api/health`, `/api/clear`
- HTML UI for trace visualization (`console/ui.py`)
- Can be extended for query results

**CLI already has:**
- `db-mcp init` — interactive setup wizard
- `db-mcp start` — MCP server (stdio mode)
- `db-mcp console` — trace viewer UI
- `db-mcp status`, `list`, `use`, `sync`, `pull` — connection management
- Claude Desktop auto-configuration

### What's Missing for Electron

| Component | Status | Effort |
|-----------|--------|--------|
| db-mcp binary | ✅ Done | — |
| CI/CD for binaries | ✅ Done | — |
| HTTP mode for MCP | ❌ Missing | 2 days |
| Query store (SQLite) | ❌ Missing | 3 days |
| Query results endpoint | ❌ Missing | 2 days |
| Electron shell | ❌ Missing | 1 week |
| React UI | ❌ Missing | 1 week |
| Deep link handler | ❌ Missing | 2 days |
| Auto-updater | ❌ Missing | 2 days |
| Code signing | ❌ Missing | 1 day |

### Implementation Phases (Revised)

**Phase 1: Extend db-mcp for Desktop** (1 week)

Already done:
- ✅ PyInstaller binary (67MB)
- ✅ Multi-platform CI/CD
- ✅ Console server on port 8384

To add:
- [ ] `db-mcp serve --http` — HTTP transport for MCP (vs stdio)
- [ ] Query store module (SQLite in `~/.db-mcp/queries.db`)
- [ ] `/api/queries` — list recent queries
- [ ] `/api/queries/{id}` — get query metadata
- [ ] `/q/{id}` — HTML page with results grid

**Phase 2: Electron Shell** (1 week)

New `apps/db-mcp-desktop/` package:
- [ ] Basic Electron + React setup (Vite)
- [ ] Sidecar manager (spawn/kill db-mcp binary)
- [ ] Main window with connection status
- [ ] IPC bridge for renderer ↔ main communication
- [ ] Tray icon with quick actions

**Phase 3: Desktop UI** (1 week)

- [ ] Connection manager (list, add, edit, remove)
- [ ] Query results grid (MUI X Data Grid)
- [ ] Schema browser (tree view)
- [ ] Onboarding wizard (reuse `db-mcp init` flow)

**Phase 4: Deep Links + Polish** (1 week)

- [ ] Register `db-mcp://` protocol handler
- [ ] Handle `db-mcp://q/{id}` → open query results
- [ ] Auto-updater (electron-updater + GitHub Releases)
- [ ] Code signing (Apple Developer + Windows EV cert)
- [ ] Installer configs (DMG, NSIS)

### What We Ship When

| Milestone | Deliverable | Users Served |
|-----------|-------------|--------------|
| Today | `db-mcp` CLI + binary | CLI users, Claude Desktop |
| Phase 1 | `db-mcp serve --http` + query store | Advanced users, scripting |
| Phase 2 | Basic Electron app | Early adopters |
| Phase 3 | Full desktop UI | General users |
| Phase 4 | Signed, auto-updating | Production users |

### Estimated Total: 4 weeks

Much faster than original 12-14 week estimate because:
1. Binary build pipeline already exists
2. Console server provides HTTP foundation
3. CLI already handles connection management
4. No Python rewrite needed

### Multiple Delivery Targets (Preserved)

The sidecar approach still supports multiple delivery modes:

| Delivery | Description | Bundle |
|----------|-------------|--------|
| `pip install db-mcp` | Python package (existing) | ~5MB |
| Standalone binary | PyInstaller bundle | ~50MB |
| Electron Desktop | Full GUI app | ~200MB |
| Claude Desktop MCP | Config points to binary | ~50MB |

Users choose based on their needs. Electron is optional, not forced.

---

## Open Questions

1. **PyInstaller binary size** — Need to test actual size with all dependencies. Target: <80MB per platform.
2. **Python startup time** — Cold start latency for sidecar. May need preloading strategy.
3. **Claude Desktop deep link testing** — Verify `db-mcp://` protocol works or fallback to HTTP.
4. **Metrics layer scope** — Include in desktop or keep cloud-only?
5. **Offline LLM** — Should desktop support local models (Ollama) for air-gapped environments?

---

## Deep Linking: Query Result URLs

### The Goal

When Claude executes a query via DB-MCP MCP tools, return a clickable URL that opens the full results in a dedicated viewer:

```
Query executed successfully. 847 rows returned.

[View full results](db-mcp://q/8f3a2b1c)

| col_a | col_b | ... |
|-------|-------|-----|
(showing first 10 rows)
```

### How MCP Tool Responses Handle Links

Per the [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools), tools can return **resource links**:

```json
{
  "type": "resource_link",
  "uri": "db-mcp://q/8f3a2b1c",
  "name": "Query Results",
  "description": "847 rows from analytics.events",
  "mimeType": "application/json"
}
```

**Key insight**: The MCP protocol supports URIs, but whether they're clickable depends on the **client** (Claude Desktop, Cursor, etc.), not the protocol.

### Claude Desktop Link Handling (Unknown)

Claude Desktop is an Electron app. Standard Electron apps use `shell.openExternal()` to open URLs:

```ts
// Typical Electron link handling
shell.openExternal('https://example.com')  // Opens in browser
shell.openExternal('db-mcp://q/abc123')    // Opens registered protocol handler
```

**What we don't know**:
- Does Claude Desktop pass custom protocols to `shell.openExternal()`?
- Does it sanitize URLs to http/https only?
- Is there an allowlist mechanism?

**Action needed**: Test with a simple custom protocol to verify behavior.

### Custom Protocol Registration in Electron

If DB-MCP ships as an Electron app, registering `db-mcp://` protocol:

**Main process setup:**
```ts
import { app, shell } from 'electron'

// Register on startup
if (process.defaultApp) {
  // Dev mode
  app.setAsDefaultProtocolClient('db-mcp', process.execPath, [path.resolve(process.argv[1])])
} else {
  // Production
  app.setAsDefaultProtocolClient('db-mcp')
}

// macOS: handle URL when app is running
app.on('open-url', (event, url) => {
  event.preventDefault()
  handleDeepLink(url)  // url = "db-mcp://q/abc123"
})

// Windows/Linux: URL comes via second-instance event
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', (event, argv) => {
    const url = argv.find(arg => arg.startsWith('db-mcp://'))
    if (url) handleDeepLink(url)
    mainWindow?.focus()
  })
}

function handleDeepLink(url: string) {
  const parsed = new URL(url)
  // db-mcp://q/abc123 → pathname = "/abc123", hostname = "q"
  if (parsed.hostname === 'q') {
    const queryId = parsed.pathname.slice(1)
    mainWindow.webContents.send('navigate', `/query/${queryId}`)
  }
}
```

**Build configuration (electron-builder):**
```json
{
  "protocols": [{
    "name": "DB-MCP Query Results",
    "schemes": ["db-mcp"]
  }]
}
```

**Platform differences:**

| Platform | Event | Cold Start Handling |
|----------|-------|---------------------|
| macOS | `open-url` | Works automatically |
| Windows | `second-instance` | URL in `process.argv` |
| Linux | `second-instance` | URL in `process.argv` |

Reference: [Electron Deep Links Documentation](https://www.electronjs.org/docs/latest/tutorial/launch-app-from-url-in-another-app)

### Fallback: localhost HTTP Server

If custom protocols don't work with Claude Desktop, fallback to HTTP:

```
http://localhost:8384/q/abc123
```

**Pros:**
- Works universally (any browser, any client)
- No protocol registration needed
- Already have console server on port 8384

**Cons:**
- Requires DB-MCP server to be running when link clicked
- Less "native" feel
- Port conflicts possible

**Implementation:**
```ts
// Extend existing console server
app.get('/q/:queryId', async (req, res) => {
  const { queryId } = req.params
  const metadata = await queryStore.get(queryId)
  
  if (!metadata) {
    return res.status(404).send('Query not found')
  }
  
  // Option A: Return JSON for programmatic access
  if (req.accepts('json')) {
    const results = await fetchQueryResults(metadata)
    return res.json(results)
  }
  
  // Option B: Return HTML page with data grid
  return res.send(renderQueryPage(metadata))
})
```

### URL Schema Comparison

| Schema | Example | Pros | Cons |
|--------|---------|------|------|
| `db-mcp://q/{id}` | `db-mcp://q/abc123` | Native feel, launches app | May be blocked by Claude |
| `http://localhost:8384/q/{id}` | `http://localhost:8384/q/abc123` | Always works | Requires server running |
| `file://` | `file://~/.db-mcp/results/abc123.html` | Offline | Security warnings, ugly |

### Recommended Approach

**Primary**: Try `db-mcp://` custom protocol
**Fallback**: `http://localhost:8384/q/{id}`
**Detection**: At runtime, check if custom protocol works; if not, use HTTP

```ts
// In MCP tool response
function getQueryResultUrl(queryId: string): string {
  if (customProtocolSupported()) {
    return `db-mcp://q/${queryId}`
  }
  return `http://localhost:${CONSOLE_PORT}/q/${queryId}`
}
```

### Query Store Design

To support deep linking, we need persistent query metadata:

```ts
// SQLite schema
CREATE TABLE queries (
  id TEXT PRIMARY KEY,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  connection_name TEXT NOT NULL,
  sql TEXT NOT NULL,
  row_count INTEGER,
  execution_time_ms INTEGER,
  expires_at DATETIME,  -- Optional TTL
  metadata JSON         -- columns, types, etc.
);
```

**Storage options:**

| Approach | Store | Pros | Cons |
|----------|-------|------|------|
| Metadata only | SQLite | Small, fast | Must re-run query for data |
| Metadata + sample | SQLite | Quick preview | Limited rows |
| Full results | SQLite + files | Complete data | Storage grows |

**Recommendation**: Store metadata + first 1000 rows. Full data re-fetched on demand.

### Integration with Delivery Targets

| Delivery | Deep Link Support | Implementation |
|----------|-------------------|----------------|
| CLI (`npx`) | HTTP only | Console server on localhost |
| Standalone binary | HTTP only | Same |
| Electron Desktop | Custom protocol + HTTP | Full support |

The custom `db-mcp://` protocol is **Electron-only**. CLI/binary users get HTTP URLs.

---

## Desktop App Packaging

### Positioning

**DBeaver/DataGrip-style but AI-native** — a compelling angle for developer tools market.

### Packaging Tools Comparison

| Tool | Bundle Size | Pros | Cons |
|------|-------------|------|------|
| **electron-builder** | ~150MB | Most mature, all platforms, auto-update built-in | Large bundles |
| **electron-forge** | ~150MB | Official tooling, better TS/Webpack integration | Newer, less battle-tested |
| **Tauri** | ~10MB | Tiny bundles, Rust backend | Must rewrite db-mcp or bundle as sidecar |
| **Wails** | ~15MB | Go backend, small bundles | Go rewrite needed |

**Recommendation**: Start with **electron-builder** — fastest to ship, widest reach, most documentation.

### Output Formats by Platform

| Platform | Formats | Notes |
|----------|---------|-------|
| macOS | DMG, pkg | Notarization required for distribution |
| Windows | NSIS, MSI, portable | Code signing critical (SmartScreen) |
| Linux | AppImage, deb, rpm, snap | AppImage most portable |

### Bundling the db-mcp Binary (Sidecar Pattern)

Similar to how VS Code bundles language servers:

```
app/
├── resources/
│   └── bin/
│       ├── db-mcp-darwin-arm64
│       ├── db-mcp-darwin-x64
│       ├── db-mcp-linux-x64
│       └── db-mcp-win-x64.exe
├── main/
│   └── index.ts
└── renderer/
    └── ...
```

**Main process spawns sidecar:**
```ts
import { spawn } from 'child_process'
import path from 'path'

function getDbMcpPath(): string {
  const platform = process.platform
  const arch = process.arch
  const ext = platform === 'win32' ? '.exe' : ''
  const binary = `db-mcp-${platform}-${arch}${ext}`
  
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'bin', binary)
  }
  return path.join(__dirname, '../../resources/bin', binary)
}

function startDbMcp() {
  const dbMcpPath = getDbMcpPath()
  const proc = spawn(dbMcpPath, ['serve', '--port', '8384'], {
    stdio: ['pipe', 'pipe', 'pipe']
  })
  
  proc.stdout.on('data', (data) => console.log(`db-mcp: ${data}`))
  proc.stderr.on('data', (data) => console.error(`db-mcp error: ${data}`))
  
  return proc
}
```

**electron-builder config:**
```json
{
  "extraResources": [{
    "from": "resources/bin/",
    "to": "bin/",
    "filter": ["**/*"]
  }],
  "mac": {
    "target": ["dmg", "zip"],
    "hardenedRuntime": true,
    "gatekeeperAssess": false
  },
  "win": {
    "target": ["nsis", "portable"]
  },
  "linux": {
    "target": ["AppImage", "deb"]
  }
}
```

### Communication Patterns

| Pattern | Pros | Cons |
|---------|------|------|
| **stdio (MCP native)** | Standard MCP transport, simple | Binary must support stdio |
| **HTTP localhost** | Easy debugging, browser tools | Port management |
| **IPC (named pipes)** | Fast, no port conflicts | Platform-specific |

**Recommendation**: HTTP on localhost (already have console server) with stdio as backup for pure MCP mode.

### Hybrid Mode: Local Binary vs Remote Service

The desktop app should support both:

```ts
interface DbMcpConnection {
  mode: 'local' | 'remote'
  localBinaryPath?: string
  remoteUrl?: string  // e.g., "https://db-mcp.mycompany.com"
}

// Settings UI lets user choose:
// - "Use bundled db-mcp" (default)
// - "Connect to remote service" (enterprise)
```

**Enterprise use case**: Centralized db-mcp service with shared connections, audit logs, etc.

### Distribution Channels

| Channel | Pros | Cons | Target |
|---------|------|------|--------|
| **Direct download** | Full control, no fees | Trust issues, manual updates | Early adopters |
| **GitHub Releases** | Free, auto-update support, dev trust | Must self-host signing | OSS users |
| **Mac App Store** | Trust, discovery | 30% cut, sandboxing restrictions | Broad consumer |
| **Microsoft Store** | Trust, MSIX | 15% cut, review delays | Windows enterprise |
| **Homebrew Cask** | Dev-friendly install | No auto-update UI | macOS devs |
| **winget** | Dev-friendly install | No auto-update UI | Windows devs |

**Recommended rollout:**

1. **Phase 1**: Direct download + GitHub Releases (auto-update via electron-updater)
2. **Phase 2**: Homebrew Cask + winget for developer reach
3. **Phase 3**: App stores if consumer demand materializes

### Code Signing Requirements

**Critical**: Unsigned apps are increasingly painful on modern OS.

| Platform | Requirement | Cost | Process |
|----------|-------------|------|---------|
| macOS | Developer ID + Notarization | $99/year Apple Developer | Sign → Notarize → Staple |
| Windows | EV Code Signing Certificate | $300-500/year | Sign with HSM or cloud signing |
| Linux | None required | Free | Optional GPG signing |

**macOS notarization flow:**
```bash
# 1. Sign the app
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name" \
  --options runtime \
  YourApp.app

# 2. Create DMG
hdiutil create -volname "YourApp" -srcfolder YourApp.app -ov YourApp.dmg

# 3. Notarize
xcrun notarytool submit YourApp.dmg --apple-id "you@email.com" --wait

# 4. Staple
xcrun stapler staple YourApp.dmg
```

**electron-builder handles this** if you provide credentials in env vars.

### Auto-Update Architecture

```
┌─────────────────┐     Check for updates      ┌──────────────────┐
│  Desktop App    │ ─────────────────────────→ │  Update Server   │
│  (electron-     │                            │  (S3/GitHub/     │
│   updater)      │ ←───────────────────────── │   custom)        │
└─────────────────┘     latest.yml + binary    └──────────────────┘
```

**Options:**
- **GitHub Releases**: Free, works great for OSS
- **S3 + CloudFront**: More control, private releases
- **Custom server**: Full control, enterprise features

**electron-updater config:**
```ts
import { autoUpdater } from 'electron-updater'

autoUpdater.setFeedURL({
  provider: 'github',
  owner: 'apelogic-ai',
  repo: 'db-mcp-desktop'
})

autoUpdater.checkForUpdatesAndNotify()
```

### Build Matrix

For CI/CD (GitHub Actions example):

```yaml
jobs:
  build:
    strategy:
      matrix:
        include:
          - os: macos-latest
            arch: arm64
          - os: macos-latest
            arch: x64
          - os: ubuntu-latest
            arch: x64
          - os: windows-latest
            arch: x64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npm run build
      - run: npx electron-builder --${{ matrix.os == 'macos-latest' && 'mac' || matrix.os == 'windows-latest' && 'win' || 'linux' }} --${{ matrix.arch }}
      - uses: actions/upload-artifact@v4
        with:
          name: dist-${{ matrix.os }}-${{ matrix.arch }}
          path: dist/
```

---

## Appendix: TypeScript Library References

### Database Drivers
- PostgreSQL: `pg` - https://node-postgres.com/
- ClickHouse: `@clickhouse/client` - https://clickhouse.com/docs/en/integrations/language-clients/nodejs
- Trino: `trino-client` - https://www.npmjs.com/package/trino-client
- MySQL: `mysql2` - https://github.com/sidorares/node-mysql2
- SQL Server: `tedious` - https://github.com/tediousjs/tedious

### MCP
- Official SDK: `@modelcontextprotocol/sdk` - https://github.com/modelcontextprotocol/typescript-sdk

### SQL Parsing
- `node-sql-parser` - https://github.com/taozhi8833998/node-sql-parser
- `pgsql-ast-parser` - https://github.com/oguimbal/pgsql-ast-parser

### Electron Packaging
- `electron-builder` - https://www.electron.build/
- `electron-forge` - https://www.electronforge.io/
- `electron-updater` - https://www.electron.build/auto-update

### Alternatives to Electron
- Tauri - https://tauri.app/
- Wails - https://wails.io/
