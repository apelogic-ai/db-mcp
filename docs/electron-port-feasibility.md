# DB-MCP Desktop Application Architecture

**Status**: Active Development  
**Created**: 2026-01-21  
**Updated**: 2026-01-23  
**Decision**: Next.js (web-first) + Electron shell (future) + Python sidecar (BICP agent)

## Executive Summary

This document defines the architecture for db-mcp's desktop/web application. After evaluating multiple approaches, we've chosen:

1. **Web-first development**: Next.js static export served by Python sidecar
2. **Protocol**: BICP (Business Intelligence Client Protocol) for UI-sidecar communication
3. **Electron later**: Same React components, different routing layer
4. **Unified codebase strategy**: Share 60-80% of UI code between web and desktop

This approach ships faster, preserves existing Python investment, and maintains flexibility for future Electron packaging.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Delivery Layer                            │
├────────────────────┬────────────────────────────────────────┤
│   Web (Now)        │   Electron Desktop (Future)            │
│   Next.js 14       │   Electron + React Router              │
│   Static Export    │   Bundled with sidecar binary          │
└─────────┬──────────┴─────────────────┬──────────────────────┘
          │                            │
          │  BICP (JSON-RPC)           │  BICP (JSON-RPC)
          │  HTTP + WebSocket          │  HTTP + WebSocket
          ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Python Sidecar (db-mcp)                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 BICP Agent                           │   │
│  │  • initialize (capability negotiation)               │   │
│  │  • schema/list, schema/describe                     │   │
│  │  • query/create, query/candidates, query/approve    │   │
│  │  • semantic/search                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 MCP Server                           │   │
│  │  • For Claude Desktop integration                   │   │
│  │  • Existing tools: validate_sql, run_sql, etc.     │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Database Layer                       │   │
│  │  • SQLAlchemy introspection                         │   │
│  │  • PostgreSQL, ClickHouse, Trino, MySQL, MSSQL     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Why This Architecture

### Sidecar Pattern (Battle-Tested)

The sidecar pattern is proven at scale:
- **VS Code** bundles language servers
- **Cursor** bundles AI backends
- **GitHub Desktop** bundles Git binary

**Benefits:**
- Preserves 12,000+ lines of Python (SQLAlchemy introspection, MCP server, validation)
- Ships in weeks, not months
- Single binary distribution via PyInstaller

### BICP Protocol

We created BICP (Business Intelligence Client Protocol) to standardize UI-agent communication:

```
┌─────────────────┐         ┌─────────────────┐
│   BICP Client   │ ─────── │   BICP Agent    │
│   (TypeScript)  │  JSON-  │   (Python)      │
│                 │  RPC    │                 │
│  • UI           │ ◄─────► │  • db-mcp       │
│  • CLI tools    │         │  • Future BI    │
│  • BI tools     │         │    backends     │
└─────────────────┘         └─────────────────┘
```

**Why not just HTTP REST?**
- Query lifecycle needs streaming (candidates → approval → progress → results)
- Session management for conversation context
- Standard message format enables multiple clients

### Web-First, Electron Later

**Why not Electron immediately?**
- Faster iteration without Electron build overhead
- Team expertise in Next.js
- Browser DevTools for debugging
- Electron is an optional wrapper, not a requirement

**Why Electron eventually?**
- Native OS integration (tray icon, deep links, auto-update)
- Bundled distribution (single download)
- Offline capability

---

## Unified Codebase Strategy

### The Challenge

Next.js router is deeply tied to file-system routing and server components. It won't work in Electron. But we can share significant code.

### What We Share (60-80%)

| Layer | Shared | Why |
|-------|--------|-----|
| React components | Yes | Pure UI, no routing deps |
| Hooks (non-routing) | Yes | Business logic |
| BICP client | Yes | Protocol abstraction |
| State management | Yes | Zustand stores |
| Utilities | Yes | Pure functions |

### What Diverges (20-40%)

| Layer | Web (Next.js) | Desktop (Electron) |
|-------|---------------|-------------------|
| Routing | App Router (`/app/`) | React Router |
| Data fetching | Server components, API routes | IPC to main process |
| Navigation | `next/link`, `useRouter` | React Router hooks |
| Auth | NextAuth, cookies | Secure storage, keychain |

### Code Structure

```
packages/
├── ui/                          # Shared UI package
│   ├── src/
│   │   ├── components/          # Routing-agnostic components
│   │   │   ├── connectors/
│   │   │   │   └── connector-card.tsx
│   │   │   ├── query/
│   │   │   │   ├── query-input.tsx
│   │   │   │   ├── candidate-card.tsx
│   │   │   │   └── result-table.tsx
│   │   │   └── ui/              # shadcn components
│   │   ├── hooks/
│   │   │   └── use-bicp.ts      # BICP client hook
│   │   └── lib/
│   │       └── bicp.ts          # BICP client
│   ├── app/                     # Next.js pages (web only)
│   │   ├── layout.tsx
│   │   ├── connectors/page.tsx
│   │   ├── context/page.tsx
│   │   ├── query/page.tsx
│   │   ├── tools/page.tsx
│   │   └── explorer/page.tsx
│   └── package.json
│
└── desktop/                     # Future Electron app
    ├── src/
    │   ├── main/                # Electron main process
    │   │   ├── index.ts
    │   │   └── sidecar.ts       # Spawn db-mcp binary
    │   └── renderer/            # React with React Router
    │       ├── App.tsx
    │       └── routes/
    ├── electron/
    └── package.json             # depends on @db-mcp/ui components
```

### Navigation Abstraction

Components should not import `next/link` or `next/navigation` directly:

```typescript
// packages/ui/src/lib/navigation.tsx
import { createContext, useContext } from 'react';

export type NavigateFn = (path: string) => void;
export const NavigationContext = createContext<NavigateFn | null>(null);

export function useAppNavigate(): NavigateFn {
  const navigate = useContext(NavigationContext);
  if (!navigate) throw new Error('NavigationContext not provided');
  return navigate;
}

// Web: provide Next.js router
// Desktop: provide React Router navigate
```

### Data Fetching Abstraction

Components call hooks, not fetch directly:

```typescript
// packages/ui/src/hooks/use-connectors.ts
export function useConnectors() {
  // Uses useBICP() under the hood
  // Web: HTTP to localhost:8080/bicp
  // Desktop: Same, or IPC if preferred
}
```

---

## Current Implementation Status

### Completed

| Component | Status | Location |
|-----------|--------|----------|
| BICP Agent (Python) | ✅ Done | `packages/core/src/db_mcp/bicp/` |
| BICP Client (TypeScript) | ✅ Done | `../bicp/packages/client-typescript/` |
| UI Server (FastAPI) | ✅ Done | `packages/core/src/db_mcp/ui_server.py` |
| Next.js project setup | ✅ Done | `packages/ui/` |
| shadcn/ui components | ✅ Done | `packages/ui/src/components/ui/` |
| Tab pages (placeholder) | ✅ Done | `packages/ui/src/app/*/page.tsx` |
| BICP initialize handshake | ✅ Done | Tested end-to-end |

### In Progress

| Component | Status | Notes |
|-----------|--------|-------|
| Connectors page UI | 🔄 Basic | BICP connection test working |
| Context Viewer | 📋 Planned | Needs schema/list, schema/describe |
| Query Console | 📋 Planned | Core BICP feature |
| Query Explorer | 📋 Planned | Migrate from Python OTel viewer |

### Future (Electron Phase)

| Component | Status | Notes |
|-----------|--------|-------|
| Electron shell | 📋 Planned | Main process + IPC |
| Sidecar manager | 📋 Planned | Spawn/kill db-mcp binary |
| Deep link handler | 📋 Planned | `db-mcp://` protocol |
| Auto-updater | 📋 Planned | electron-updater |
| Code signing | 📋 Planned | Apple + Windows certs |

---

## BICP Integration

### Protocol Specification

Full spec at: `../bicp/spec/bicp-v0.1.md`

### Key Messages

| Category | Messages | UI Usage |
|----------|----------|----------|
| Initialization | `initialize` | Connection handshake |
| Schema | `schema/list`, `schema/describe` | Context Viewer |
| Query | `query/create`, `query/candidates`, `query/approve` | Query Console |
| Semantic | `semantic/search` | Search across metrics/dimensions |

### Client-Agent Communication

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js UI (localhost:3000)                               │
│                                                             │
│  fetch('/bicp', { method: 'POST', body: jsonRpcRequest })  │
│                 │                                           │
│                 │ Next.js rewrite                          │
│                 ▼                                           │
│  http://localhost:8080/bicp                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Python Sidecar (localhost:8080)                           │
│                                                             │
│  FastAPI → DBMCPAgent.handle_request(JsonRpcRequest)       │
│                                                             │
│  Response: JsonRpcResponse with result or error            │
└─────────────────────────────────────────────────────────────┘
```

---

## Development Workflow

### Local Development

```bash
# Terminal 1: Python sidecar
cd packages/core
uv run python -m db_mcp.ui_server

# Terminal 2: Next.js dev server
cd packages/ui
npm run dev
```

Open http://localhost:3000 - Next.js proxies `/bicp` to sidecar.

### Production Build

```bash
# Build UI
cd packages/ui
npm run build  # → packages/ui/dist/

# Copy to sidecar static dir
cp -r packages/ui/dist/* packages/core/src/db_mcp/static/

# Build binary
cd packages/core
uv run python scripts/build.py
```

### CLI Command

```bash
db-mcp ui              # Start sidecar with UI
db-mcp ui --port 9000  # Custom port
```

---

## Electron Implementation (Future)

When we're ready for Electron:

### Project Setup

```bash
# Create Electron app with Vite
npm create electron-vite@latest packages/desktop
cd packages/desktop
npm install @db-mcp/ui  # shared components
```

### Main Process

```typescript
// packages/desktop/src/main/index.ts
import { app, BrowserWindow } from 'electron';
import { spawn } from 'child_process';
import path from 'path';

let sidecar: ChildProcess | null = null;

function getDbMcpPath(): string {
  const platform = process.platform;
  const arch = process.arch;
  const ext = platform === 'win32' ? '.exe' : '';
  const binary = `db-mcp-${platform}-${arch}${ext}`;
  
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'bin', binary);
  }
  return path.join(__dirname, '../../resources/bin', binary);
}

function startSidecar() {
  const dbMcpPath = getDbMcpPath();
  sidecar = spawn(dbMcpPath, ['ui', '--port', '8080'], {
    stdio: ['pipe', 'pipe', 'pipe']
  });
  
  sidecar.stdout?.on('data', (data) => console.log(`[sidecar] ${data}`));
  sidecar.stderr?.on('data', (data) => console.error(`[sidecar] ${data}`));
}

app.whenReady().then(() => {
  startSidecar();
  
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  
  win.loadURL('http://localhost:8080');  // Sidecar serves UI
});

app.on('before-quit', () => {
  sidecar?.kill();
});
```

### React Router Setup

```typescript
// packages/desktop/src/renderer/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { NavigationContext } from '@db-mcp/ui';
import { useNavigate } from 'react-router-dom';

// Import shared components
import { ConnectorsPage } from '@db-mcp/ui/components/connectors';
import { ContextPage } from '@db-mcp/ui/components/context';
import { QueryPage } from '@db-mcp/ui/components/query';

function AppRoutes() {
  const navigate = useNavigate();
  
  return (
    <NavigationContext.Provider value={navigate}>
      <Routes>
        <Route path="/" element={<ConnectorsPage />} />
        <Route path="/context" element={<ContextPage />} />
        <Route path="/query" element={<QueryPage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
      </Routes>
    </NavigationContext.Provider>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
```

### electron-builder Config

```json
{
  "appId": "ai.apelogic.db-mcp",
  "productName": "DB-MCP",
  "extraResources": [{
    "from": "resources/bin/",
    "to": "bin/",
    "filter": ["**/*"]
  }],
  "protocols": [{
    "name": "DB-MCP",
    "schemes": ["db-mcp"]
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

---

## Deep Linking

### URL Schema

| Schema | Usage |
|--------|-------|
| `db-mcp://q/{id}` | Open query results |
| `db-mcp://connect/{name}` | Switch to connection |
| `http://localhost:8080/q/{id}` | Fallback (works in web) |

### Electron Registration

```typescript
// macOS
app.on('open-url', (event, url) => {
  event.preventDefault();
  handleDeepLink(url);
});

// Windows/Linux
app.on('second-instance', (event, argv) => {
  const url = argv.find(arg => arg.startsWith('db-mcp://'));
  if (url) handleDeepLink(url);
});

function handleDeepLink(url: string) {
  const parsed = new URL(url);
  if (parsed.hostname === 'q') {
    const queryId = parsed.pathname.slice(1);
    mainWindow.webContents.send('navigate', `/explorer/${queryId}`);
  }
}
```

---

## Distribution

### Delivery Targets

| Target | Bundle | Users |
|--------|--------|-------|
| `pip install db-mcp` | ~5MB | Python developers |
| Standalone binary | ~67MB | CLI users |
| Web UI (sidecar) | ~67MB + browser | Most users (current focus) |
| Electron Desktop | ~200MB | Native app users (future) |

### Auto-Update (Electron)

```typescript
import { autoUpdater } from 'electron-updater';

autoUpdater.setFeedURL({
  provider: 'github',
  owner: 'apelogic-ai',
  repo: 'db-mcp'
});

autoUpdater.checkForUpdatesAndNotify();
```

### Code Signing

| Platform | Requirement | Cost |
|----------|-------------|------|
| macOS | Developer ID + Notarization | $99/year |
| Windows | EV Code Signing Certificate | $300-500/year |
| Linux | None required | Free |

---

## Migration Path

### Phase 1: Web UI (Current)

- Next.js serves as both dev server and static export source
- Python sidecar serves built static files + BICP endpoint
- All components in `packages/ui/`

### Phase 2: Component Extraction

- Extract routing-agnostic components to `packages/ui/src/components/`
- Create navigation abstraction
- Ensure components work without Next.js router

### Phase 3: Electron Shell

- Create `packages/desktop/` with electron-vite
- Import shared components
- Set up sidecar management
- Add deep linking, auto-update

### Phase 4: Polish

- Code signing
- Platform-specific installers (DMG, NSIS)
- Distribution via GitHub Releases
- Optional: App stores

---

## Open Questions

1. **Electron timeline**: Start Electron work after Query Console is complete?

2. **Component extraction timing**: Extract now or when Electron is imminent?

3. **IPC vs HTTP in Electron**: Keep HTTP (simpler) or switch to IPC (faster)?

4. **Tray icon scope**: Minimal (status only) or full (quick actions)?

---

## Related Documents

| Document | Relationship |
|----------|--------------|
| `ui-spec.md` | Detailed UI specification and wireframes |
| `ui-bicp-roadmap.md` | Implementation phases for UI features |
| `../bicp/spec/bicp-v0.1.md` | BICP protocol specification |
| `data-gateway.md` | UI as control plane for gateway |
| `metrics-layer.md` | Metrics surfaced via BICP semantic search |

---

## Appendix: Why Not Full TypeScript Rewrite?

We evaluated a full TypeScript rewrite but chose the sidecar pattern because:

| Factor | Full TS Rewrite | Sidecar (Chosen) |
|--------|-----------------|------------------|
| Timeline | 12-14 weeks | 4-6 weeks |
| Risk | High (no SQLAlchemy equivalent) | Low (proven pattern) |
| Python investment | Lost | Preserved |
| Introspection | Must rewrite per-dialect | Already done |
| MCP server | Rewrite to TS SDK | Keep existing |

**The killer issue**: SQLAlchemy's `inspect()` API has no TypeScript equivalent. We'd need to write ~3,000 lines of dialect-specific introspection code. The sidecar pattern avoids this entirely.
