# UI Architecture Baseline (March 2026)

This document captures the current `packages/ui` baseline and a cleanup plan focused on clarity, consistency, and maintainability.

## Scope and Goals

- Establish a shared understanding of the current UI stack and runtime model.
- Identify architecture risks that directly impact UX quality and development speed.
- Define a phased cleanup plan with low-risk first steps.

## Current Stack

- Framework: Next.js 14 App Router (`output: "export"`, static build artifacts).
- Runtime model: client-heavy React UI, talks to backend via BICP JSON-RPC.
- Language/tooling: TypeScript (strict), Tailwind CSS, ESLint, Vitest, Playwright.
- UI primitives: local shadcn-like components in `src/components/ui`.

## Runtime Architecture

1. Browser loads static Next-exported app.
2. App initializes BICP client (`/bicp`) through `BICPProvider`.
3. Pages invoke BICP methods (`call(...)`) via wrappers in `src/lib/bicp.ts`.
4. Backend responds with connection state, context files, traces, metrics, and insights.

## Codebase Shape (Today)

- App pages are still large orchestration units:
  - `src/app/config/page.tsx` (~1625 LOC)
  - `src/app/insights/page.tsx` (~1451 LOC)
  - `src/app/metrics/page.tsx` (~945 LOC)
  - `src/app/context/page.tsx` (~786 LOC)
- Shared providers:
  - `src/lib/bicp-context.tsx` (transport/session)
  - `src/lib/connection-context.tsx` (active connection + list)
  - `src/lib/context-viewer-context.tsx` (context-viewer state)
- Feature extraction has started:
  - `src/features/config/*` now holds config types/helpers/status indicator.

## Foundational Cleanup Already Landed on This Branch

- Added shared connection state via `ConnectionProvider` and `useConnections`.
- Wired global provider in app layout and updated selector to use shared switching.
- Migrated Context, Metrics, Insights, and Config pages to consume shared active connection.
- Removed duplicate/unused React hook from `src/lib/bicp.ts`.
- Started extraction of Config page internals into `src/features/config`.

## Key Gaps (Basics)

1. Page files are too large and mix concerns:
   - state orchestration, RPC calls, rendering, and business rules in one file.
2. Data-fetch patterns are inconsistent:
   - ad-hoc effects/callbacks, manual loading/error wiring per page.
3. Type boundaries are weak:
   - many page-local interfaces and ad-hoc response typing.
4. API/client ownership is blurred:
   - transport concerns and domain-specific helpers are mixed in `lib/bicp.ts`.
5. Test depth is uneven:
   - e2e coverage is good for flows, but feature-level unit tests are sparse.

## Cleanup Principles

- One source of truth for global state (active connection, initialization).
- Keep `app/*/page.tsx` thin: compose feature modules, avoid heavy business logic inline.
- Organize by feature first (`src/features/<domain>`), not by file type only.
- Encapsulate backend calls behind typed service modules per feature.
- Introduce view models/hooks that return stable `{data, loading, error, actions}`.

## Phase Plan

### Phase 1 (in progress): Foundations

- Shared active-connection provider across pages.
- Remove duplicate helpers/hooks.
- Extract obvious low-risk page internals (types/utils/ui atoms) into `features/*`.

### Phase 2: Feature Modularization

- Split each large page into:
  - `services` (BICP calls)
  - `hooks` (state + orchestration)
  - `components` (presentation)
  - `types` (feature contracts)
- Prioritize `config` and `insights` first (largest complexity).

### Phase 3: Data-Layer Consistency

- Standardize request lifecycle patterns and error handling.
- Option A: keep custom hooks but enforce common conventions.
- Option B: adopt React Query consistently (already in deps) and remove ad-hoc fetch state.

### Phase 4: UX Polish Baseline

- Normalize loading/empty/error states across pages.
- Unify connection-scoped behavior and copy.
- Define common interaction patterns for edit/save/discard flows.

## Acceptance Criteria for "Basics Complete"

- No page-level reimplementation of active-connection fetching.
- `config` and `insights` page orchestration each reduced to <500 LOC.
- Feature folders exist for all major surfaces: `config`, `context`, `metrics`, `insights`, `traces`.
- Shared typed service layer replaces direct page-level JSON-RPC payload shaping.
- Lint/build/tests pass in CI and locally.
