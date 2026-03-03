# GitBook Documentation Refresh

## Scope

This review covers all GitBook source pages under `gitbook/`:

- `gitbook/README.md`
- `gitbook/quickstart.md`
- `gitbook/install-and-configuration.md`
- `gitbook/using-cli.md`
- `gitbook/using-web-ui.md`
- `gitbook/working-with-agents.md`
- `gitbook/tools-reference.md`
- `gitbook/advanced-topics.md`

Comparison baseline was current implementation in `packages/core/src/db_mcp/`.

## Executive Summary

GitBook is directionally good, but currently has **high-impact accuracy drift** in storage model and tool availability semantics, plus **coverage gaps** for operational workflows introduced in the current codebase.

Most urgent fixes:

1. Correct connection/vault structure (`training/` vs `examples/`, rules file paths, feedback path).
2. Clarify tool exposure by mode/capabilities (avoid implying all tools are always present).
3. Expand CLI and collaboration docs for existing commands (`detach`, `prune`, `daemon`) and modern flows.

## Gap Analysis

## P0 (Critical Accuracy)

### 1) Connection structure is stale in GitBook

- GitBook currently documents `training/` in connection structure:
  - `gitbook/install-and-configuration.md:29`
- Runtime structure initializes `examples/`, `instructions/`, `learnings/`, `metrics/`:
  - `packages/core/src/db_mcp/vault/init.py:448`
- Example storage is folder-based (`examples/*.yaml`), not `training/examples.yaml`:
  - `packages/core/src/db_mcp/training/store.py:3`
  - `packages/core/src/db_mcp/training/store.py:24`

Impact:

- Users can look for/edit wrong files and misunderstand what is versioned and used by the runtime.

### 2) Tool availability semantics are under-specified

- GitBook lists broad tool sets, but does not clearly communicate mode/capability gating at per-tool level:
  - `gitbook/tools-reference.md:32`
- In code, many tools are conditional:
  - SQL tools depend on capabilities:
    - `packages/core/src/db_mcp/server.py:908`
  - `validate_sql` only when supported:
    - `packages/core/src/db_mcp/server.py:909`
  - `get_result` only with async jobs:
    - `packages/core/src/db_mcp/server.py:912`
  - Most query/training/metrics/gaps tools only in non-shell mode:
    - `packages/core/src/db_mcp/server.py:961`

Impact:

- Agent users will call tools that are not present in their mode/config and perceive server failures.

## P1 (High Priority)

### 3) CLI collaboration coverage is incomplete

- GitBook lists core collaboration commands:
  - `gitbook/using-cli.md:55`
- Code includes additional operational commands not documented:
  - `detach`:
    - `packages/core/src/db_mcp/cli/commands/collab.py:144`
  - `prune`:
    - `packages/core/src/db_mcp/cli/commands/collab.py:342`
  - `daemon`:
    - `packages/core/src/db_mcp/cli/commands/collab.py:463`

Impact:

- Missing docs for real-world maintenance workflows (cleanup and periodic sync).

### 4) Missing shell security/constraint documentation

- Shell tool has explicit allowlist and blocked patterns:
  - `packages/core/src/db_mcp/tools/shell.py:83`
  - `packages/core/src/db_mcp/tools/shell.py:106`

Impact:

- Users do not understand why certain shell commands are rejected, increasing friction and support overhead.

### 5) Default-mode behavior is not explicit enough

- CLI sets `tool_mode` to `shell` by default:
  - `packages/core/src/db_mcp/cli/connection.py:118`
- GitBook mentions modes but does not anchor docs around default user experience:
  - `gitbook/tools-reference.md:7`
  - `gitbook/advanced-topics.md:66`

Impact:

- New users expect full detailed tool surface but actually start in shell mode.

## P2 (Medium Priority)

### 6) UI docs are feature-level but not workflow-level

- Current UI page explains screens but not opinionated task playbooks:
  - `gitbook/using-web-ui.md:19`

Missing:

- “Onboard a new connection”
- “Resolve insights loop”
- “Promote discovered metrics”
- “Review and sync collaboration changes”

### 7) Agent integration docs lack edge-case guidance

- Basic setup is covered:
  - `gitbook/working-with-agents.md:12`

Missing:

- How `db-mcp agents` interacts with existing MCP entries
- Multi-agent setup strategy (all vs targeted)
- Client restart expectations and verification workflow with fallback checks

### 8) Information architecture is flat

- `gitbook/SUMMARY.md` is one-level, topic list only.
- No dedicated sections for:
  - Connector types (SQL/API/File/Metabase)
  - Multi-connection patterns
  - Troubleshooting matrix
  - Security model
  - Version migration/change management

## P3 (Nice-to-have)

### 9) Cross-doc consistency gaps beyond GitBook

- Root `README.md` also has stale `training/` structure references:
  - `README.md:161`

Not strictly GitBook scope, but this can reintroduce drift if not aligned.

## Enhancement Plan

## Phase 0: Source-of-Truth Alignment (P0)

Goal: eliminate factual drift before adding new content.

Deliverables:

1. Update GitBook file layout references to current connection artifacts.
2. Add one canonical “knowledge vault map” reused across relevant pages.
3. Add conditional tool-availability matrix in Tools Reference.

Acceptance criteria:

- Every path shown in GitBook exists in initialized connection structure.
- Tool docs indicate mode/capability conditions for each major category.

## Phase 1: Operator Workflows (P1)

Goal: improve “how to do real work” guidance.

Deliverables:

1. Expand `using-cli.md` with complete collaboration command coverage (`detach`, `prune`, `daemon`) and when to use each.
2. Add shell constraints section (allowlist/blocked patterns and implications).
3. Add “default shell mode vs detailed mode” guidance with decision tree.

Acceptance criteria:

- New user can complete setup + first query + team sync without referencing code.
- Fewer ambiguity points around “tool missing” and shell command rejection.

## Phase 2: UI and Agent Playbooks (P2)

Goal: turn feature descriptions into repeatable workflows.

Deliverables:

1. Convert `using-web-ui.md` into task-oriented playbooks (onboarding, insights triage, metrics approval, collaboration review).
2. Expand `working-with-agents.md` with validation checklist and troubleshooting paths per client.
3. Add a short “first 30 minutes” operator journey linking CLI + UI + agent docs.

Acceptance criteria:

- A first-time operator can self-serve common tasks end-to-end.
- Reduced need to infer flows from screenshots.

## Phase 3: IA + Troubleshooting (P2/P3)

Goal: make docs scalable as features grow.

Deliverables:

1. Restructure `gitbook/SUMMARY.md` into grouped sections:
   - Getting Started
   - Connections and Connectors
   - Querying and Tools
   - Collaboration
   - Operations and Troubleshooting
2. Add troubleshooting page:
   - Missing tools
   - Connection routing ambiguity
   - Schema/cache mismatches
   - Agent config not detected
   - Trace/insight visibility issues

Acceptance criteria:

- Any top user issue can be mapped to a troubleshooting entry in under 2 clicks.

## Proposed Backlog (Page-by-Page)

### `gitbook/quickstart.md`

- Add explicit note that default mode is shell.
- Add “what success looks like” with expected commands/results.

### `gitbook/install-and-configuration.md`

- Replace stale tree with current structure:
  - `examples/`, `instructions/`, `learnings/`, `metrics/`, `knowledge_gaps.yaml`, `feedback_log.yaml`.
- Clarify `connector.yaml` optionality by connector type.

### `gitbook/using-cli.md`

- Add missing collaboration commands and one-line intent for each.
- Add “daily contributor” and “master reviewer” workflows.

### `gitbook/using-web-ui.md`

- Keep screenshots but add concrete workflows and outcome checkpoints.
- Clarify how UI actions map to vault files and MCP behavior.

### `gitbook/working-with-agents.md`

- Add client-by-client verification/troubleshooting.
- Clarify manual configuration snippets and restart requirements.

### `gitbook/tools-reference.md`

- Add matrix:
  - always available
  - shell-only practical workflow
  - detailed-mode tools
  - capability-gated tools
- Add resources + prompt (`review-insights`) section.

### `gitbook/advanced-topics.md`

- Add dedicated sections:
  - Multi-connection strategy
  - Collaboration operating model
  - Migration notes and guardrails

## Suggested Execution Order

1. Phase 0 in one PR (accuracy fixes only).
2. Phase 1 in one PR (CLI/tooling operational docs).
3. Phase 2 and 3 in one or two PRs depending on reviewer bandwidth.

This sequencing minimizes user-facing confusion quickly, then improves depth.

