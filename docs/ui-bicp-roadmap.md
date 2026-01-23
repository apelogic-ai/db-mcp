# UI + BICP Implementation Roadmap

**Status**: Draft  
**Created**: 2025-01-23

## Overview

This document outlines the implementation plan for integrating the db-mcp UI with BICP (Business Intelligence Client Protocol). The goal is to build a reference BICP client that demonstrates the protocol's value while providing a production-ready local analytics experience.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     db-mcp UI (Next.js)                     │
│                     BICP Client Reference Implementation    │
└─────────────────────────────┬───────────────────────────────┘
                              │ BICP (JSON-RPC)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Sidecar (DBMCP)                   │
│              BICP Agent + MCP Server (dual protocol)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Foundation

**Goal**: Establish project structure and basic connectivity.

### 0.1 Project Setup

- [x] Create `packages/ui/` Next.js project with App Router
- [x] Configure static export (`output: 'export'` in next.config.js)
- [x] Set up Tailwind CSS
- [ ] Set up shadcn/ui components
- [ ] Configure dev proxy to Python sidecar
- [ ] Add build script to output to `packages/core/static/`

### 0.2 Python BICP Endpoint

- [x] Create `packages/core/src/db_mcp/bicp/` module
- [x] Implement JSON-RPC router in FastAPI
- [x] Add `/bicp` POST endpoint for request-response
- [x] Add `/bicp/stream` WebSocket for notifications
- [x] Implement `initialize` message with capability negotiation

### 0.3 Basic UI Shell

- [x] Create app layout with tab navigation
- [ ] Implement placeholder pages for all 5 tabs
- [x] Add BICP client library (`lib/bicp.ts`)
- [ ] Verify `initialize` handshake works end-to-end

### 0.4 CLI Integration

- [x] Add `db-mcp ui` command to start UI server
- [x] Serve static files from `static/` directory
- [ ] Auto-open browser on launch
- [x] Add `--port` flag for custom port

**Deliverable**: Empty UI shell that connects to sidecar via BICP.

---

## Phase 1: Data Connectors Tab

**Goal**: Manage data sources through the UI.

### 1.1 Connector List

- [ ] Create connector card component
- [ ] Display existing connections from config
- [ ] Show status indicators (connected/error/unknown)
- [ ] Show onboarding status for each connector

### 1.2 Add Connector Flow

- [ ] "Add New" dropdown with connector types
- [ ] Database connector form (name, connection string, type)
- [ ] CSV connector form (name, file path)
- [ ] Form validation and error display

### 1.3 Connector Management

- [ ] Test connection button (triggers `initialize`)
- [ ] Enable/disable toggle
- [ ] Edit connector configuration
- [ ] Remove connector (with confirmation)

### 1.4 Configuration API

- [ ] `GET /api/connectors` — list all
- [ ] `POST /api/connectors` — create new
- [ ] `PUT /api/connectors/:id` — update
- [ ] `DELETE /api/connectors/:id` — remove
- [ ] `POST /api/connectors/:id/test` — test connection

**Deliverable**: Fully functional connector management.

---

## Phase 2: Context Viewer Tab

**Goal**: Browse and edit semantic layer using BICP schema discovery.

### 2.1 Schema Tree

- [ ] Implement tree view component (react-arborist)
- [ ] Load tree structure via `schema/list`
- [ ] Expand nodes to show schemas → tables
- [ ] Show metrics under tables

### 2.2 Table Details Panel

- [ ] Call `schema/describe` on table selection
- [ ] Display table description, row count estimate
- [ ] Show columns with types and semantic annotations
- [ ] Show relationships (foreign keys)
- [ ] Show defined metrics

### 2.3 Semantic Search

- [ ] Add search input at top of tree
- [ ] Call `semantic/search` on input
- [ ] Display search results (metrics, dimensions)
- [ ] Click result to navigate to source table

### 2.4 Context Editing

- [ ] "Edit Descriptions" button on table panel
- [ ] Inline editing for table/column descriptions
- [ ] Save changes to knowledge vault
- [ ] "Add Metric" flow for defining new metrics

### 2.5 Folder Organization

- [ ] Create user-defined folders
- [ ] Drag connectors into folders
- [ ] Persist folder structure in config

**Deliverable**: Full schema browsing and semantic search.

---

## Phase 3: Query Console Tab

**Goal**: Natural language querying with BICP query lifecycle.

### 3.1 Query Input

- [ ] Text input for natural language queries
- [ ] Session management (create/end sessions)
- [ ] Data source selector (from enabled connectors)
- [ ] "Ask" button to submit query

### 3.2 Candidate Display

- [ ] Receive `query/candidates` notification
- [ ] Display candidate cards with:
  - SQL (syntax highlighted)
  - Confidence score
  - Explanation
  - Cost estimate
  - Recommended visualization
- [ ] Expand/collapse for multiple candidates

### 3.3 Approval Flow

- [ ] "Approve" button → `query/approve`
- [ ] "Edit SQL" button → modal with Monaco editor
- [ ] "Reject" button → `query/reject` with reason input
- [ ] Request revision option

### 3.4 Execution Progress

- [ ] Receive `query/progress` notifications
- [ ] Display progress bar with:
  - Percent complete
  - Rows processed
  - Elapsed time
  - Status message
- [ ] Cancel button → `query/cancel`

### 3.5 Results Display

- [ ] Receive `query/result` notifications
- [ ] Streaming row population
- [ ] Tab switcher: Chart / Table / SQL
- [ ] Table view with TanStack Table:
  - Sorting
  - Filtering
  - Pagination
  - Column resize

### 3.6 Chart Rendering

- [ ] Interpret BICP visualization config
- [ ] Render recommended chart type (Recharts):
  - Line chart
  - Bar chart
  - Pie chart
  - Single value KPI
- [ ] Chart type switcher (alternatives)
- [ ] Apply formatting (currency, dates, etc.)

### 3.7 Insights Display

- [ ] Show `insights` array from `query/complete`
- [ ] Styled insight cards
- [ ] Copy insight text

### 3.8 Query Refinement

- [ ] "Refine" input below results
- [ ] Send `query/refine` with previous query ID
- [ ] Maintain conversation history in UI
- [ ] Show previous queries in session

### 3.9 Export

- [ ] Export dropdown (CSV, Excel, JSON)
- [ ] Copy SQL to clipboard
- [ ] Copy results to clipboard

**Deliverable**: Complete natural language query experience.

---

## Phase 4: Query Explorer Tab

**Goal**: Observability into query execution.

### 4.1 Timeline View

- [ ] List recent queries with timestamps
- [ ] Show query source (BICP vs MCP)
- [ ] Display query lifecycle states
- [ ] Expand to show sub-operations

### 4.2 Query Details

- [ ] Click query to show details panel
- [ ] Display executed SQL
- [ ] Show cost metrics (bytes scanned, time)
- [ ] Show result summary

### 4.3 Filtering

- [ ] Filter by time range
- [ ] Filter by data source
- [ ] Filter by status (success/failed)
- [ ] Filter by query type (BICP/MCP)

### 4.4 Error Inspection

- [ ] Highlight failed queries
- [ ] Show error details and stack trace
- [ ] Link to relevant documentation

### 4.5 Re-run Capability

- [ ] "Re-run" button on query
- [ ] Opens Query Console with pre-filled input
- [ ] Maintains original context

**Deliverable**: Full query observability.

---

## Phase 5: MCP Tools Tab

**Goal**: Control MCP tool exposure to Claude Desktop.

### 5.1 Tool List

- [ ] Tree view grouped by connector
- [ ] List available tools per connector
- [ ] Show tool description and purpose

### 5.2 Tool Management

- [ ] Checkbox to enable/disable tools
- [ ] Show usage statistics (invocation count)
- [ ] Global exposed tools summary

### 5.3 Configuration Persistence

- [ ] Save exposed tools to config
- [ ] Reload on MCP server restart

**Deliverable**: MCP tool access control.

---

## Phase 6: Onboarding Integration

**Goal**: Guided setup for new data sources.

### 6.1 Onboarding Wizard

- [ ] Detect new/incomplete connectors
- [ ] Show onboarding progress indicator
- [ ] Step-by-step wizard overlay

### 6.2 Discovery Phase

- [ ] Progress bar during schema introspection
- [ ] Live counts (tables, columns discovered)
- [ ] Error handling for connection issues

### 6.3 Review Phase

- [ ] List all discovered tables
- [ ] Bulk ignore patterns (regex input)
- [ ] Table-by-table description entry
- [ ] AI-assisted description generation

### 6.4 Domain Building Phase

- [ ] Trigger domain model generation
- [ ] Preview generated domain model
- [ ] Edit and regenerate options

### 6.5 Completion

- [ ] Summary of configured context
- [ ] "Start Querying" CTA
- [ ] Link to documentation

**Deliverable**: Smooth onboarding for new data sources.

---

## Phase 7: Polish & Production

**Goal**: Production-ready release.

### 7.1 Error Handling

- [ ] Global error boundary
- [ ] Toast notifications for errors
- [ ] Retry mechanisms for network failures
- [ ] Graceful degradation

### 7.2 Loading States

- [ ] Skeleton loaders for all async operations
- [ ] Optimistic updates where appropriate
- [ ] Request deduplication

### 7.3 Accessibility

- [ ] Keyboard navigation
- [ ] Screen reader support
- [ ] Focus management
- [ ] Color contrast compliance

### 7.4 Performance

- [ ] Code splitting per tab
- [ ] Virtualized lists for large datasets
- [ ] Memoization for expensive renders
- [ ] Bundle size optimization

### 7.5 Testing

- [ ] Unit tests for BICP client
- [ ] Component tests with Testing Library
- [ ] E2E tests with Playwright
- [ ] BICP message validation tests

### 7.6 Documentation

- [ ] User guide for each tab
- [ ] Keyboard shortcuts reference
- [ ] Troubleshooting guide

### 7.7 Binary Distribution

- [ ] PyInstaller spec update for static files
- [ ] Test on macOS (arm64, x64)
- [ ] Test on Linux (x64)
- [ ] Test on Windows (x64)
- [ ] Update release workflow

**Deliverable**: Production-ready v1.0 release.

---

## Phase 8: Electron Shell (Optional)

**Goal**: Native desktop experience.

### 8.1 Electron Setup

- [ ] Create Electron wrapper project
- [ ] Load UI from sidecar HTTP server
- [ ] Spawn sidecar as child process
- [ ] Handle sidecar lifecycle

### 8.2 Native Features

- [ ] System tray icon
- [ ] Native menus
- [ ] Auto-launch on startup
- [ ] Deep linking (db-mcp:// URLs)

### 8.3 Distribution

- [ ] macOS: DMG installer
- [ ] Windows: MSI/NSIS installer
- [ ] Linux: AppImage/deb/rpm

**Deliverable**: Native desktop app.

---

## Dependency Graph

```
Phase 0 (Foundation)
    │
    ├──► Phase 1 (Connectors)
    │        │
    │        └──► Phase 6 (Onboarding)
    │
    ├──► Phase 2 (Context Viewer)
    │        │
    │        └──► Phase 3 (Query Console)
    │                 │
    │                 └──► Phase 4 (Explorer)
    │
    └──► Phase 5 (MCP Tools)

All Phases ──► Phase 7 (Polish)
                   │
                   └──► Phase 8 (Electron) [Optional]
```

---

## Milestones

| Milestone | Phases | Description |
|-----------|--------|-------------|
| **M1: Skeleton** | 0 | UI shell connects to sidecar |
| **M2: Config** | 0, 1 | Manage connectors through UI |
| **M3: Browse** | 0, 1, 2 | Browse schemas and semantic layer |
| **M4: Query** | 0, 1, 2, 3 | Natural language querying works |
| **M5: Observe** | 0-4 | Full observability |
| **M6: Complete** | 0-5 | All tabs functional |
| **M7: Onboard** | 0-6 | Guided onboarding |
| **M8: Release** | 0-7 | Production v1.0 |
| **M9: Native** | 0-8 | Electron app |

---

## Technical Decisions

### Confirmed

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI Framework | Next.js 14+ | Team expertise, static export support |
| Styling | Tailwind CSS | Rapid development, consistent design |
| Components | shadcn/ui | Accessible, customizable, Tailwind-native |
| BICP Transport | HTTP + WebSocket | HTTP for requests, WS for streaming |
| Chart Library | Recharts | React-native, good defaults, customizable |
| Table Library | TanStack Table | Headless, performant, feature-rich |
| Tree View | react-arborist | Performant, accessible, drag-drop support |
| Code Editor | Monaco | Industry standard, SQL support |

### To Decide

| Decision | Options | Notes |
|----------|---------|-------|
| State Management | Zustand vs Jotai vs Redux Toolkit | Zustand recommended for simplicity |
| Form Handling | React Hook Form vs Formik | RHF recommended |
| API Client | Custom vs tRPC vs orval | Custom BICP client, orval for config API |
| Testing | Jest vs Vitest | Vitest recommended for speed |
| E2E Testing | Playwright vs Cypress | Playwright recommended |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| BICP spec changes | Version protocol, maintain backwards compat |
| Performance with large schemas | Virtualize tree, lazy-load children |
| Chart rendering complexity | Start with basic types, expand incrementally |
| WebSocket reliability | Reconnection logic, message queuing |
| Binary size bloat | Analyze bundle, tree-shake aggressively |

---

## Success Criteria

### M4 (Query Milestone)

- [ ] User can add a database connector
- [ ] User can browse tables and columns
- [ ] User can ask natural language questions
- [ ] User can approve/reject query candidates
- [ ] User can see results in table and chart form
- [ ] User can refine queries conversationally

### M8 (Release Milestone)

- [ ] All 5 tabs fully functional
- [ ] Onboarding wizard works end-to-end
- [ ] Binary works on macOS, Linux, Windows
- [ ] Documentation complete
- [ ] No critical bugs in 1 week of testing

---

## Open Questions

1. **Query history persistence**: Store in sidecar SQLite or browser localStorage?
   - Recommendation: Sidecar SQLite for cross-session persistence

2. **Multi-user support**: Should sessions be isolated per user?
   - Recommendation: Defer to Phase 2, single-user for v1

3. **Offline mode**: Should UI work without LLM connectivity?
   - Recommendation: Graceful degradation (SQL passthrough works, NL fails)

4. **Custom visualizations**: Allow users to define chart configs?
   - Recommendation: Defer, rely on agent recommendations for v1

5. **Plugin system**: Allow third-party UI extensions?
   - Recommendation: Defer to v2

---

## Next Steps

1. **Immediate**: Set up `packages/ui/` with Next.js
2. **This week**: Implement Phase 0 (Foundation)
3. **Next week**: Start Phase 1 (Connectors) + Phase 2 (Context Viewer) in parallel
4. **Week 3**: Phase 3 (Query Console) — the core experience
