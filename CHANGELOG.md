# Changelog

All notable changes to **db-mcp** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- _Add entries here during development._

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

