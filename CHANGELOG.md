# Changelog

All notable changes to **db-mcp** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- _Add entries here during development._

## [0.4.50] - 2026-02-06

### Added

- **Collaborative git sync protocol**: master/collaborator model for shared knowledge vaults via git
- **`.collab.yaml` manifest**: tracks team members, roles, and sync configuration
- **`db-mcp collab` CLI group**: `init`, `join`, `sync`, `merge`, `status`, `members` subcommands
- **Smart file classification**: auto-merge additive files (examples, learnings, traces); PR for shared-state (schema, rules, metrics)
- **Background sync loop**: periodic pull/push in MCP server lifespan (default 60m, configurable)
- **GitHub PR integration**: auto-opens PRs for shared-state changes via `gh` CLI
- **Git branch operations**: `checkout`, `fetch`, `merge`, `cherry_pick`, `current_branch`, `branch_exists`, `diff_names`, `push_branch` on `NativeGitBackend`
- **Migration**: updates existing `.gitignore` to allow `.collab.yaml`

## [0.4.49] - 2026-02-06

### Fixed

- **Codex TOML round-trip**: `_dict_to_toml` now recursively handles arbitrary nesting depth, preserving `env` maps and other nested structures in `~/.codex/config.toml`
- **Spurious `[mcp_servers]` header**: intermediate-only tables no longer emit empty section headers in generated TOML

## [0.4.48] - 2026-02-04

**Release Date:** February 4, 2026

## Overview

This release overhauls the Insights page with a unified **SQL Patterns** card, a new **Save as Learning** flow for auto-corrected errors, and several fixes for API connectors and the training pipeline.

## Highlights

### Unified SQL Patterns Card

The separate "Repeated Queries" and "Errors & Failures" cards have been merged into a single **SQL Patterns** card with expandable accordion rows. Each row shows:

- Tool label and badges (e.g. `4x`, `auto-corrected`)
- Truncated SQL preview (click to expand full multiline SQL)
- Timestamps (first/last seen)
- Save action (`Save as Example` or `Save as Learning`)

Sections within the card: Repeated Queries, Auto-corrected Errors, Hard Errors, Validation Failures.

### Save as Learning for Auto-corrected Errors

Auto-corrected SQL errors (soft failures) now show the failing SQL and a **Save as Learning** button. Clicking it expands the row to reveal:

- Full multiline SQL in a scrollable `<pre>` block
- Pre-filled description extracted from the error message (e.g. "Table 'lending.deposits' does not exist -- use correct table name")
- Save/Cancel buttons

Saved learnings are stored as training examples with an `[ERROR PATTERN]` prefix, helping the agent avoid the same mistakes in future sessions.

### Saved State Persists Across Refresh

Previously, saving an example or learning showed a brief "Saved" state that reverted on the next 5-second auto-refresh. Now the backend's `insights/analyze` response includes `is_saved` for errors whose SQL matches a saved training example, so the saved state persists correctly.

### Improved Knowledge Capture Card

The Knowledge Capture card now shows intent descriptions inline instead of hiding them behind click-to-expand. Error patterns and regular examples are displayed in separate labeled sections with distinct icons.

## Bug Fixes

### API Connector: Correct Dialect Display

API connectors (e.g. Dune Analytics) previously showed "duckdb" as the dialect in the connectors list. Now they display the API title from discovery (e.g. "Dune Analytics API") or derive a name from the base URL.

### `get_provider_dir` Fixed for Named Connections

`get_provider_dir(provider_id)` was ignoring the provider_id argument and always returning the active connection path. This caused `is_example` checks and save operations to fail when the provider_id didn't match the active connection. Fixed to return `~/.db-mcp/connections/{provider_id}` when a provider_id is given.

### SQL Extraction from `api_execute_sql` Spans

`_extract_sql()` now parses SQL from the `attrs.args` JSON field (where `api_execute_sql` stores its arguments), in addition to the existing `attrs.sql` and `attrs.sql.preview` paths. This enables the Save as Learning feature for SQL-like API connectors.

### Playwright E2E Port Conflict

Fixed E2E tests failing when port 3000 was occupied by another application. Changed default dev server port to 3177 and set `reuseExistingServer: false`.

## Files Changed

| File | Change |
|------|--------|
| `packages/ui/src/app/insights/page.tsx` | Unified SQL Patterns card, Save as Learning flow, improved Knowledge Capture card |
| `packages/ui/src/lib/bicp.ts` | Added `sql`, `is_saved`, `example_id` fields to error type |
| `packages/ui/e2e/insights.spec.ts` | 4 new E2E tests for SQL Patterns and save flows |
| `packages/ui/playwright.config.ts` | Port fix (3177), `reuseExistingServer: false` |
| `packages/core/src/db_mcp/bicp/traces.py` | SQL extraction from args JSON, `is_saved` for errors, SQL attached to error traces |
| `packages/core/src/db_mcp/bicp/agent.py` | API title display for connectors, API connection test improvements |
| `packages/core/src/db_mcp/connectors/api.py` | Store `api_title` from discovery, use it as dialect |
| `packages/core/src/db_mcp/onboarding/state.py` | Fix `get_provider_dir` to respect provider_id |
| `packages/core/tests/test_traces.py` | 13 new tests for SQL extraction and `is_saved` behavior |

## Testing

- **362 Python tests** passing (13 new)
- **69 E2E tests** passing (4 new)
- Lint clean (ruff, ESLint, TypeScript)


## [0.4.47] - 2026-02-04

**Release Date:** February 4, 2026

## Overview

This release introduces **multi-agent configuration support**, making it easier to set up db-mcp across different MCP-compatible AI agents. Instead of manually editing JSON/TOML config files, you can now configure db-mcp for Claude Desktop, Claude Code, and OpenAI Codex with a single command.

## Highlights

### Automatic Agent Detection & Configuration

db-mcp now automatically detects which MCP-compatible agents are installed on your system and offers to configure them all at once:

```bash
db-mcp init mydb
# Detects: Claude Desktop [yes], Claude Code [yes], OpenAI Codex [no]
# Prompts: Configure db-mcp for which agents?
#   [1] All detected agents  ← default
#   [2] Select specific agents
#   [3] Skip agent configuration
```

### New `db-mcp agents` Command

Manage agent configurations anytime with the new dedicated command:

```bash
# Interactive selection
db-mcp agents

# List detected agents
db-mcp agents --list

# Configure all detected agents
db-mcp agents --all

# Configure specific agents
db-mcp agents -A claude-desktop
db-mcp agents -A claude-code -A codex
```

## New Features

### 1. Multi-Agent Registry

A centralized agent registry with auto-detection for:

| Agent | Config Location | Format | Detection Method |
|-------|----------------|--------|------------------|
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | JSON | Config file or app presence |
| **Claude Code** | `~/.claude.json` | JSON | Config file or `claude` CLI |
| **OpenAI Codex** | `~/.codex/config.toml` | TOML | Config directory or `codex` CLI |

### 2. Intelligent Configuration

- **Preserves existing servers**: Only adds/updates the `db-mcp` entry, keeps all other MCP servers intact
- **Legacy cleanup**: Automatically removes old `dbmeta` entries
- **Cross-platform**: Works on macOS, Windows, and Linux

### 3. Flexible TOML Support

- Uses Python's built-in `tomllib` for reading TOML (Python 3.11+)
- Custom TOML writer implementation (no external dependencies)
- Full support for OpenAI Codex's config format

## Usage Examples

### First-Time Setup

```bash
# Initialize a new connection
db-mcp init production

# db-mcp detects installed agents and prompts:
# Detected MCP-compatible agents:
#   [1] Claude Desktop
#   [2] Claude Code
#
# Configure db-mcp for which agents?
# Choice [1]: ← press Enter to configure all
#
# [yes] Claude Desktop configured
# [yes] Claude Code configured
# [yes] Configured 2/2 agent(s)
```

### Reconfigure Agents Later

```bash
# List what's installed
db-mcp agents --list
# Detected MCP agents:
#   [yes] Claude Desktop
#     Config: ~/Library/Application Support/Claude/claude_desktop_config.json
#   [yes] Claude Code
#     Config: ~/.claude.json

# Configure all detected agents
db-mcp agents --all
# [yes] Claude Desktop configured
# [yes] Claude Code configured
# [yes] Configured 2/2 agent(s)
```

### Configure Specific Agents

```bash
# Only configure Claude Desktop
db-mcp agents -A claude-desktop

# Configure multiple specific agents
db-mcp agents -A claude-code -A codex
```

## Technical Details

### Agent Detection Logic

1. **Config File Check**: Looks for agent config files in standard locations
2. **App/CLI Check**: Falls back to checking if app is installed or CLI is available
3. **Platform-Aware**: Adjusts paths based on OS (macOS/Windows/Linux)

### Configuration Process

For each agent:

1. Load existing config (if any)
2. Add/update `db-mcp` server entry with correct binary path
3. Remove legacy `dbmeta` entry (if present)
4. Save config while preserving all other servers

### Config Format Examples

**Claude Desktop/Code (JSON)**:
```json
{
  "mcpServers": {
    "db-mcp": {
      "command": "/usr/local/bin/db-mcp",
      "args": ["start"]
    }
  }
}
```

**OpenAI Codex (TOML)**:
```toml
[mcp_servers.db-mcp]
command = "/usr/local/bin/db-mcp"
args = ["start"]
```

## Testing

This release includes comprehensive test coverage:

- **21 new tests** for agent detection, configuration, and TOML handling
- All tests passing [ok]
- No regressions in existing functionality

## Important Notes

### ChatGPT Desktop Not Supported

ChatGPT Desktop uses UI-only configuration (Settings → Connectors → Developer mode) and does not support local config file configuration. You'll need to configure it manually through the UI.

### Binary Path Detection

db-mcp intelligently detects the binary path:
- If running from PyInstaller bundle: uses the executable path
- If symlinked at `~/.local/bin/db-mcp`: uses the symlink (for auto-updates)
- Otherwise: uses `db-mcp` command

## Upgrade Instructions

### From v0.4.45

1. Update to v0.4.47:
   ```bash
   # If installed via pip
   pip install --upgrade db-mcp
   
   # If using binary
   # Download new binary and replace existing one
   ```

2. Reconfigure agents (optional but recommended):
   ```bash
   db-mcp agents --all
   ```

3. Restart your MCP agents (Claude Desktop, Claude Code, etc.)

## Bug Fixes

- None (feature-only release)

## Security

- No security changes in this release

## Documentation Updates

- Added agent registry documentation
- Updated CLI command reference
- Added multi-agent setup examples

## Credits

This feature was developed in response to user feedback requesting easier configuration across multiple AI agents.

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md#0446---2026-02-04) for complete details.

## Coming Soon

Stay tuned for upcoming features:
- Additional agent support (Cursor, Windsurf, etc.)
- Config validation and health checks
- Agent-specific settings and preferences

---

**Questions or Issues?** Report them at https://github.com/apelogic-ai/db-mcp/issues


## [0.4.46] - 2026-02-04

## Highlights
- Multi-agent configuration support - automatically configure db-mcp for Claude Desktop, Claude Code, and OpenAI Codex

## Breaking changes
- None

## Features
- **New `db-mcp agents` command** - Interactive configuration for multiple MCP-compatible agents
  - `db-mcp agents` - Interactive selection of detected agents
  - `db-mcp agents --list` - Show all detected agents on your system
  - `db-mcp agents --all` - Configure all detected agents at once
  - `db-mcp agents -A claude-desktop -A codex` - Configure specific agents
- **Auto-detection of installed agents** - Detects Claude Desktop, Claude Code, and OpenAI Codex
- **Integrated into `db-mcp init`** - Automatically prompts to configure detected agents during setup
- **Support for multiple config formats**:
  - JSON for Claude Desktop and Claude Code (`mcpServers`)
  - TOML for OpenAI Codex (`mcp_servers`)
- **Preserves existing MCP servers** - Only adds/updates db-mcp entry, keeps other servers intact
- **Legacy cleanup** - Automatically removes old `dbmeta` entries when configuring

## Fixes
- None

## Security
- None

## Upgrade notes
After upgrading, you can reconfigure agents at any time with:
```bash
db-mcp agents --all  # Configure all detected agents
```

Supported agents:
- **Claude Desktop** (`~/.../Claude/claude_desktop_config.json`)
- **Claude Code** (`~/.claude.json`)
- **OpenAI Codex** (`~/.codex/config.toml`)

Note: ChatGPT Desktop uses UI-only configuration and is not supported for auto-configuration.

## Known issues
- None

## [0.4.45] - 2026-02-03

## Highlights
- New `api_execute_sql` tool for SQL-like APIs (Dune Analytics, etc.)

## Breaking changes
- None

## Features
- Added `api_execute_sql(sql="...")` tool specifically for SQL-like API connectors
- Keeps SQL execution separate from REST endpoint queries (`api_query`) and true SQL databases (`run_sql`)

## Fixes
- Fixed async polling to handle Dune's `QUERY_STATE_COMPLETED` status format
- Added support for `is_execution_finished` flag in status responses

## Security
- None

## Upgrade notes
For Dune Analytics and similar SQL-like APIs, use `api_execute_sql`:
```
api_execute_sql(sql="SELECT * FROM dex_solana.trades LIMIT 10")
```

## Known issues
- None


## [0.4.44] - 2026-02-03

## Highlights
- 

## Breaking changes
- None

## Features
- 

## Fixes
- 

## Security
- None

## Upgrade notes
- None

## Known issues
- None


## [0.4.43] - 2026-02-03

## Highlights
- Fixed Dune Analytics async polling to correctly detect query completion

## Breaking changes
- None

## Features
- None

## Fixes
- Fixed async polling to handle Dune's `QUERY_STATE_COMPLETED` status format (was only checking lowercase `complete`)
- Added support for `is_execution_finished` flag in status responses

## Security
- None

## Upgrade notes
- None

## Known issues
- None


## [0.4.42] - 2026-02-03

## Highlights
- SQL-like API connectors (Dune Analytics, etc.) now fully supported with direct SQL execution

## Breaking changes
- None

## Features
- Added `execute_sql()` support for API connectors with `supports_sql: true` capability
- Automatic handling of async SQL APIs that return execution IDs and require polling
- Configurable `sql_field` per endpoint (defaults to `sql` for Dune compatibility)
- Response extraction handles multiple formats: Dune (`result.rows`), standard REST (`data`, `rows`, `results`), and columnar (`columns` + `rows` arrays)

## Fixes
- None

## Security
- None

## Upgrade notes
To use with Dune Analytics, configure your `connector.yaml`:

```yaml
type: api
base_url: https://api.dune.com/api/v1
auth:
  type: header
  header_name: X-DUNE-API-KEY
  token_env: API_KEY
capabilities:
  supports_sql: true
  sql_mode: api_sync

endpoints:
  - name: execute_sql
    path: /sql/execute
    method: POST
    body_mode: json
  - name: execution_status
    path: /execution/{execution_id}/status
  - name: execution_results
    path: /execution/{execution_id}/results
```

## Known issues
- None


## [0.4.41] - 2026-02-03

## Highlights
- Fixed macOS binary being killed on launch due to corrupted code signature

## Breaking changes
- None

## Features
- None

## Fixes
- Fixed macOS binaries failing to launch with "Killed: 9" error. The GitHub Actions runner's PyInstaller was producing binaries with invalid adhoc signatures. Added explicit `codesign --force --sign -` step after build to ensure valid signatures.

## Security
- None

## Upgrade notes
- If you previously installed 0.4.40 and it wouldn't run, simply re-install: `curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh`

## Known issues
- None


## [0.4.40] - 2026-02-02

## Highlights
- API connectors: treat SQL-like endpoints correctly (stops misclassifying certain API endpoints as SQL)

## Breaking changes
- None

## Features
- None

## Fixes
- Core: improve SQL detection/handling for API connectors (fixes edge cases around “SQL-like” endpoints)

## Security
- None

## Upgrade notes
- None

## Known issues
- None


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

