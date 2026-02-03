# Changelog

All notable changes to **db-mcp** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- _Add entries here during development._

## [0.4.39] - 2026-02-02

## Highlights
- CI: stabilize Playwright E2E workflows (use Bun, avoid `npm ci` lock mismatch)
- E2E: make the `/bicp` dev-server proxy disable-able so mocked tests don’t depend on a local backend

## Breaking changes
- None

## Features
- UI: configurable BICP proxy target via `BICP_PROXY_TARGET` (defaults to `http://localhost:8080`)

## Fixes
- CI: `e2e-real-connectors` workflow now uses Bun (`bun install`, `bunx playwright ...`)
- CI/E2E: disable Next rewrites in mocked E2E via `DISABLE_BICP_PROXY=1` to prevent `ECONNREFUSED` during Playwright route mocking

## Security
- None

## Upgrade notes
- If you run the UI dev server with a non-default BICP backend, set `BICP_PROXY_TARGET`.
- For mocked Playwright E2E runs, set `DISABLE_BICP_PROXY=1`.

## Known issues
- None


## [0.4.38] - 2026-02-02

## Highlights
- Expanded connector support: **Metabase connector** + improved API/file/sql connector plumbing.
- Added **real E2E connector tests** (Playwright) and CI workflow scaffolding.

## Breaking changes
- None

## Features
- Core: add **Metabase connector**.
- Core: generalize SQL handling and improve connector abstractions.
- UI/CI: add Playwright **real connectors** E2E coverage (Postgres + Polymarket + file connector).

## Fixes
- Connector/server: improve API connector and server/tool integration.
- Tests: add coverage for run_sql/server/connectors.

## Security
- None

## Upgrade notes
- None

## Known issues
- macOS Gatekeeper may block running the downloaded release binary unless the artifact is signed/notarized.


## [0.4.37] - 2026-02-02

## Highlights
- Improved API connector auth configuration: you can now specify a **custom header name** (e.g. `X-Api-Key`).

## Breaking changes
- None

## Features
- UI: API connector form now supports **Header Name** when auth type is `header`.
- UI: auth field labeling is smarter for `query_param` (shows “Query Param Name” and defaults placeholder to `api_key`).

## Fixes
- Connector generation: when auth type is `header`, connector config now persists `header_name` to `connector.yaml`.

## Security
- None

## Upgrade notes
- None

## Known issues
- None

