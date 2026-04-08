# Miner: Knowledge Extraction from Agent Traces

**Codename:** miner
**Status:** Design
**Date:** 2026-04-08

---

## Concept

Coding agents (Claude Code, Codex, Cursor, OpenCode) leave structured
traces of every session — messages, tool calls, reasoning chains,
outcomes. These traces are the highest-quality signal source available:
they record not just what happened, but the full reasoning chain of
WHY, including approaches tried and abandoned, user corrections, and
knowledge gaps encountered.

Miner is an opt-in daemon that watches agent trace directories, extracts
knowledge artifacts from structured patterns, and routes them through
human-in-the-loop curation to a knowledge vault. Optionally syncs
approved artifacts to a corporate knowledge vault via git.

---

## What's in the traces

### Agent trace locations and formats

| Agent | Location | Format | Structure |
|---|---|---|---|
| Claude Code | `~/.claude/projects/{path}/` | JSONL | message, tool_use, tool_result, thinking |
| Codex (OpenAI) | `~/.codex/sessions/YYYY/MM/DD/` | JSONL | response_item, event_msg, function_call |
| Cursor | `~/.cursor/logs/` | JSONL | Composer steps, edits, file reads |
| OpenCode | `~/.opencode/sessions/` | JSONL | Messages, tool calls |

### Observed data (from this machine)

| | Claude Code | Codex |
|---|---|---|
| Sessions (all projects) | 32+ | 83 |
| Date range | Mar 9 → Apr 8 | Feb 2 → Apr 7 |
| Total size | 113 MB | 3.5 GB |
| JSONL entries | 19,929 | 208,938 |
| Tool calls | 4,564 | 38,924 |
| Top tool | Bash (41%) | exec_command (74%) |

### Entry types by agent

**Claude Code entries:**
- `type: user` — user messages (prompts, corrections, feedback)
- `type: assistant` — agent responses (with `content` blocks)
- `content[].type: tool_use` — tool invocation (name, input)
- `content[].type: tool_result` — tool output
- `message.usage` — input/output/cache token counts per response

**Codex entries:**
- `type: response_item` — messages, function calls, function results
- `type: event_msg` — task lifecycle (started, complete, aborted)
- `payload.type: function_call` — tool invocation (name, arguments)
- `payload.type: function_call_output` — tool result
- `payload.type: reasoning` — chain-of-thought
- `payload.type: task_complete` — session summary with `last_agent_message`

---

## Extractable knowledge patterns

### Deterministic (no LLM needed)

These patterns are structural — detectable by matching on trace entry
types and sequences:

**Retry pattern** — tool call failed → same tool with different input → succeeded

```
entry[n]:   tool_use(Bash, "uv run pytest tests/ -v")  → error
entry[n+1]: tool_use(Bash, "uv run pytest tests/ -v -x --tb=short")  → success
→ Knowledge: "add -x --tb=short when tests fail for better diagnostics"
```

**User correction** — user message immediately after agent output that
contradicts or redirects

```
entry[n]:   assistant: "I'll use the Textual framework..."
entry[n+1]: user: "that's the wrong ACP. look for the one authored by Zed"
→ Knowledge: rule or correction
```

**Search gap** — agent searched for a term, got no results or wrong results

```
entry[n]:   tool_use(Grep, pattern="fiscal_year")  → no matches
entry[n+1]: user: "fiscal year starts April 1 in this org"
→ Knowledge: gap + resolution
```

**Repeated edit pattern** — same structural edit applied across 3+ files

```
entry[n]:   tool_use(Edit, file_a, old→new)
entry[n+k]: tool_use(Edit, file_b, similar old→similar new)
entry[n+m]: tool_use(Edit, file_c, similar old→similar new)
→ Knowledge: cross-cutting convention or pattern
```

**Task completion summary** — Codex `task_complete.last_agent_message`
contains a pre-summarized conclusion

```
payload.type: task_complete
payload.last_agent_message: "The package split is still carrying too many
  permanent-looking compatibility shims..."
→ Knowledge: architectural insight, ready-made
```

### Agentic (LLM interprets)

For ambiguous patterns, the miner's LLM reads the trace context and
drafts a knowledge artifact:

- Multi-step debugging sessions → extract the root cause + fix as a decision
- Long research → user reading sessions → extract what was learned
- Agent consulted docs, then generated different code → extract which doc was useful and how

---

## Skill monitoring

Beyond traces, miner monitors the **skill ecosystem** — what's
installed, what's used, what's stale.

### Skill locations

| Agent | Location | Format |
|---|---|---|
| Claude Code (global) | `~/.claude/skills/*/SKILL.md` | Markdown + YAML frontmatter |
| Claude Code (project) | `.claude/skills/*/SKILL.md` | Markdown + YAML frontmatter |
| Codex (global) | `~/.codex/skills/*/SKILL.md` | Markdown + YAML frontmatter |
| Codex (project) | `.codex/skills/*/` | Various |
| Cursor | `.cursor/rules/*.md` | Markdown |
| Codex AGENTS.md | `~/.codex/AGENTS.md` | Markdown (global instructions) |

### What to track

| Signal | Source | What it means |
|---|---|---|
| Skill installed | File watch on skill dirs | New capability available |
| Skill invoked | Trace JSONL (Skill tool call) | Capability is actively used |
| Skill never used (30d) | Cross-reference installed vs invoked | Dead skill — remove or investigate |
| Skill used 20+ times | Invocation count from traces | Validated — candidate for org promotion |
| AGENTS.md / CLAUDE.md edited | File watch | Manual knowledge codification |
| Permission rules accumulated | `~/.codex/rules/default.rules` | Behavioral trust patterns |

### Observed on this machine

| Agent | Skill | Used? |
|---|---|---|
| Claude Code | `release` | Yes (2x) |
| Claude Code | `playwright-cli` | No (installed, never invoked) |
| Claude Code | `update-config` | Yes (1x) |
| Codex | `playwright` | Yes (via MCP tools) |
| Codex | `playwright-interactive` | Unknown |
| Codex | `pdf` | Unknown |
| Codex | AGENTS.md (db-mcp preferences) | Active (36 skill references in traces) |

---

## Architecture

```
Agent trace dirs        Skill dirs          Git repos
~/.claude/projects/     ~/.claude/skills/   ~/dev/*/
~/.codex/sessions/      ~/.codex/skills/
                        .claude/skills/
        │                    │                  │
        ▼                    ▼                  ▼
   ┌─────────────────────────────────────────────────┐
   │  miner daemon                                   │
   │                                                 │
   │  Trace watcher     Skill watcher    Git watcher │
   │  (new JSONL lines) (file changes)   (commits)   │
   │       │                 │               │       │
   │       ▼                 ▼               ▼       │
   │  ┌──────────────────────────────────────────┐   │
   │  │ Parsers                                  │   │
   │  │  claude.ts — Claude Code JSONL           │   │
   │  │  codex.ts  — Codex JSONL + SQLite        │   │
   │  │  cursor.ts — Cursor logs                 │   │
   │  │  git.ts    — commit history (existing)   │   │
   │  │  skills.ts — skill install/usage         │   │
   │  └──────────────────────────────────────────┘   │
   │       │                                         │
   │       ▼                                         │
   │  Extractors (deterministic)                     │
   │  ├── retries: tool fail → retry → succeed       │
   │  ├── corrections: user contradicts agent        │
   │  ├── gaps: search miss + user explains          │
   │  ├── conventions: repeated edit pattern          │
   │  ├── summaries: task_complete messages           │
   │  ├── skill_usage: invocation tracking            │
   │  └── skill_lifecycle: install, stale, promoted   │
   │       │                                         │
   │       ▼                                         │
   │  Interpreter (agentic, optional)                │
   │  ├── complex trace → decision artifact          │
   │  └── ambiguous pattern → draft rule             │
   │       │                                         │
   │       ▼                                         │
   │  Signal store (connections/me/signals/)          │
   └─────────────────────────────────────────────────┘
        │
        ▼
   Human-in-the-loop review (miner review / sigint review)
        │
        ├── approve → local knowledge vault
        ├── edit + approve → local vault
        └── dismiss → logged
        │
        ▼
   Daily sync → corp knowledge vault (git push)
```

### Relationship to sigint

Miner is an extension of sigint, not a separate tool. Sigint already
has the daemon, signal store, review flow, and interpreter. Miner adds:

1. **New source: trace watcher** — alongside git watcher
2. **New parsers** — per-agent JSONL parsing
3. **New extractors** — trace-specific patterns (retries, corrections, gaps)
4. **Skill monitoring** — watch skill dirs, track usage from traces

The CLI is the same:

```bash
sigint watch ~/dev/ --traces --skills    # enable trace + skill monitoring
sigint review                            # same curation flow
sigint status                            # includes trace + skill stats
sigint sync --remote git@corp/vault.git  # daily sync to corp
```

---

## Configuration

```yaml
# ~/.db-mcp/config.yaml
sigint:
  sources:
    git:
      paths: [~/dev/]
      enabled: true
    traces:
      enabled: true                   # master switch
      claude_code: true               # watch ~/.claude/projects/
      codex: true                     # watch ~/.codex/sessions/
      cursor: false                   # not opted in
    skills:
      enabled: true
      watch_dirs:
        - ~/.claude/skills/
        - ~/.codex/skills/
      track_usage: true               # correlate with trace invocations
      stale_threshold_days: 30        # flag unused skills after 30d
      promotion_threshold: 20         # suggest org promotion after 20 uses

  # What to extract from traces
  extractors:
    retries: true
    corrections: true
    gaps: true
    conventions: true
    task_summaries: true              # Codex task_complete messages

  # Privacy controls (local)
  privacy:
    capture_file_contents: false      # never store actual code from traces
    strip_secrets: true               # redact secrets before shipping
    exclude_projects: []              # project paths to skip entirely

  # Centralized shipping
  ship:
    enabled: false
    endpoint: null                    # https://miner.acme.com/api/ingest
    api_key_env: MINER_API_KEY        # auth for ingest endpoint
    schedule: hourly                  # hourly | daily | realtime
    redact_secrets: true              # deterministic regex redaction pre-ship
    # Secret patterns: AWS keys, DB URLs, GitHub tokens, etc.
    # ~99% true positive coverage, ~5% false positive rate
    # See "Observed data" section for validation

  # Local knowledge sync (git-based, for approved artifacts only)
  sync:
    enabled: false
    remote: null                      # git@github.com:acme/knowledge.git
    schedule: daily
    branch: main
```

---

## Privacy and opt-in

Miner reads local agent traces. This is sensitive data — it contains
prompts, code, reasoning, and potentially secrets.

### Two modes

**Local-only mode** (default): traces are read locally, knowledge
artifacts are extracted and stored locally, human reviews before
anything enters the vault. No data leaves the machine.

**Centralized mode** (opt-in): traces are scanned for secrets, redacted,
and shipped to an org-hosted lakehouse for cross-correlation, analytics,
security scanning, and DX diagnostics. Raw traces with secrets redacted
leave the machine; the four lakehouse pipelines process them centrally.

### Principles

1. **Explicit opt-in per agent.** Each agent source must be individually
   enabled. Nothing is watched by default.
2. **Secret redaction before shipping.** Deterministic regex scanning
   catches secrets (AWS keys, DB passwords, GitHub tokens, etc.) and
   replaces them with `[REDACTED]` before any data leaves the machine.
   Coverage: ~99% of real secrets, ~5% false positive rate (validated
   against 236K lines of real traces — see Observed data section).
3. **Three layers of filtering:** (a) regex patterns for structural
   matches, (b) entry-type filtering to exclude reasoning tokens,
   (c) project/path exclusions for repos with legitimate key material.
4. **Project exclusion.** Specific project paths can be excluded entirely
   (e.g., client projects under NDA).
5. **Local knowledge curation stays local.** The human-in-the-loop
   review and personal knowledge vault are never shipped centrally.
   Only redacted traces go to the lakehouse; only approved artifacts
   go to the corp knowledge vault (via git sync).
6. **Secret detection is a feature, not a bug.** Finding secrets in
   traces is a security signal — it means secrets management tooling
   has a gap. The miner reports these findings to the security team
   (via the Security pipeline) so the tooling gets fixed.

### What miner NEVER does

- Read traces from agents the user hasn't opted in
- Ship unredacted secrets to the centralized lakehouse
- Auto-apply knowledge without human review
- Access trace files from other users on shared machines

---

## Build plan

Five components, clean separation.

```
1. Local agent ──► 2. Ingestor API ──► S3 (lakehouse)
   (scan, redact,     (receive,            │
    ship)              normalize,           ├──► 3. Knowledge miner → corp vault
                       store)               ├──► 4. Analytics → dashboards
                                            ├──► 5. Security → alerts
                                            └──► 6. DX diagnostics → DevEx
```

### Component 1 — Local agent (daemon/CLI)

Runs on each developer's machine. Scans agent trace directories,
redacts secrets, ships to the centralized ingestor idempotently.
Also runs local knowledge extraction for the personal vault.

**Subphases:**

**1a. Trace parsers**
- Claude Code JSONL parser (`~/.claude/projects/*/`)
- Codex JSONL parser (`~/.codex/sessions/YYYY/MM/DD/`)
- Extensible to Cursor, OpenCode

**1b. Secret scanner + redactor**
- Three-layer deterministic filtering:
  (a) regex patterns (AWS `AKIA...`, `postgres://...`, `ghp_...`, etc.)
  (b) entry-type filtering (exclude reasoning tokens to reduce false positives)
  (c) project/path exclusions (skip repos with legitimate key material)
- Replaces matches with `[REDACTED:pattern_name]`
- Reports detections locally before redacting (security signal)
- Validated: ~99% true positive, ~5% false positive on 236K real lines

**1c. Shipper**
- Idempotent: tracks cursor (last shipped position per trace file)
- Ships redacted JSONL to ingestor API endpoint
- Retries on failure, does not re-ship already-sent entries
- Configurable schedule: realtime, hourly, daily

**1d. Local knowledge extraction** (existing sigint functionality)
- Deterministic extractors: retries, corrections, gaps, conventions
- Agentic interpretation (optional, via ACP)
- Skill monitoring: install/usage tracking, staleness detection
- Human-in-the-loop review (`sigint review`)
- Local vault writes

**Files:**
- `packages/sigint/src/sources/traces.ts` — trace directory watcher
- `packages/sigint/src/parsers/claude.ts` — Claude Code JSONL parser
- `packages/sigint/src/parsers/codex.ts` — Codex JSONL parser
- `packages/sigint/src/security/scanner.ts` — secret detection + redaction
- `packages/sigint/src/shipper.ts` — idempotent ingestor client
- `packages/sigint/src/sources/skills.ts` — skill directory watcher
- `packages/sigint/src/extractors/trace.ts` — retry, correction, gap patterns
- `packages/sigint/src/extractors/skill_usage.ts` — skill usage correlation

**Gate:** `sigint watch ~/dev/ --traces --ship` scans Claude Code
traces, redacts 3 AWS keys, ships redacted JSONL to the ingestor.

### Component 2 — Ingestor API

Receives trace data from local agents, normalizes across agent formats,
stores to S3 (lakehouse). Stateless HTTP service.

**Responsibilities:**
- Authentication (API key per developer/team)
- Schema normalization: Claude Code + Codex + Cursor → unified schema
- Deduplication (idempotency keys from local agent)
- Storage: raw zone (per-agent format) + normalized zone (unified schema)
- Metadata: developer ID, project, agent type, timestamp range

**Normalized schema:**

```
NormalizedEntry:
  id: string                    # hash of content for dedup
  timestamp: ISO8601
  agent: claude_code | codex | cursor | opencode
  developer: string             # anonymizable
  project: string               # repo or workspace name
  entry_type: message | tool_call | tool_result | reasoning | task_summary
  role: user | assistant | system | tool
  tool_name: string | null      # normalized (Bash, exec_command → "shell")
  tool_input_summary: string | null  # structured, no raw code
  tool_success: boolean | null
  content_preview: string | null # first 200 chars, secrets redacted
  token_usage: { input, output, cache_read } | null
  session_id: string
  turn_id: string | null
```

**Files:** separate service (not in sigint package)

**Gate:** ingestor receives traces from 2 developers, normalizes
Claude Code + Codex into the same schema, queryable in the lakehouse.

### Components 3–6 — Processing pipelines

All four pipelines read from the normalized zone in the lakehouse.
They run independently — different schedules, different consumers.

**Component 3 — Knowledge miner (centralized)**

Same extractors as local, but cross-correlated across developers.
Proposes org-level artifacts. Curator reviews and promotes to corp vault.

- Schedule: daily or on-demand
- Output: proposed artifacts → curator → corp knowledge vault (git)
- Key value: "5 developers hit the same EMFILE bug" (invisible locally)

**Component 4 — Analytics engine**

SQL queries + dashboards over the normalized trace data.

- Schedule: continuous / hourly refresh
- Output: dashboards (Grafana, Metabase, or similar)
- Key metrics: tool usage, token costs, error rates, adoption curves,
  sessions per developer, MCP tool value, skill usage rates

**Component 5 — Security scanner (centralized)**

Runs secret patterns over incoming data (defense in depth — the local
agent redacts, but the central scanner catches anything missed).
Also detects behavioral policy violations.

- Schedule: on ingest (streaming) or hourly batch
- Output: alerts (Slack, PagerDuty, email)
- Key signals: secrets that survived local redaction, prod DB access,
  unapproved MCP servers, unusual data access patterns

**Component 6 — DX diagnostics**

Aggregates friction signals across developers to identify systemic
tooling and documentation gaps.

- Schedule: weekly batch
- Output: report for DevEx team / tech leads
- Key signals: repeated questions about same topic (doc gap),
  same config fought by multiple devs (broken DX), new hire session
  length anomalies (onboarding gap), flaky test retries (infra issue)

### Corp knowledge sync

Orthogonal to the pipelines — approved artifacts from the knowledge
miner (Component 3) are pushed to a corporate knowledge vault via git.

```bash
sigint sync --remote git@github.com:acme/knowledge.git
```

This is the same git-based sync from the local agent, but triggered
by the centralized curator rather than individual developers.

---

## Centralized architecture: Lakehouse

The local miner (Phases 1–4) handles individual developer workflows.
For organizational knowledge, a centralized architecture adds
cross-correlation, analytics, security scanning, and DX diagnostics.

### Trace collection

Developers opt in to ship traces to a central lakehouse. Traces are
preprocessed locally before shipping:

| Preprocessing level | What's stripped | Recommendation |
|---|---|---|
| **Raw** | Nothing | Maximum value, maximum risk |
| **Redact secrets** | Regex-strip secrets → `[REDACTED]` | **Recommended.** Safe, preserves behavioral data |
| **Strip file contents** | Remove tool_result payloads | Loses code context |
| **Metadata only** | Keep only tool names, timestamps, success/fail | Minimal risk, minimal value |

**Recommended:** redact secrets locally (the security scanner runs
BEFORE shipping to catch and alert), then ship everything else. Full
behavioral data for all processing paths, no credential exposure in
the central store.

```
Developer machines (opt-in)
├── Claude Code traces ──┐
├── Codex traces ────────┤── local secret scan + redaction
├── Cursor traces ───────┤
└── skill/config changes ┘
         │
         ▼
    Ingest API / collector
         │
         ▼
    ┌─────────────────────────────┐
    │  Lakehouse                  │
    │  (append-only, immutable)   │
    │                             │
    │  Raw zone:                  │
    │    traces_claude/           │
    │    traces_codex/            │
    │    skill_events/            │
    │                             │
    │  Processed zone:            │
    │    normalized_tool_calls/   │
    │    normalized_sessions/     │
    │    secret_detections/       │
    │    error_patterns/          │
    │                             │
    │  Curated zone:              │
    │    knowledge_artifacts/     │
    │    security_findings/       │
    │    dx_diagnostics/          │
    └─────────────────────────────┘
         │
         ├──► Path 1: Knowledge miner ──► corp vault
         ├──► Path 2: Analytics engine ──► dashboards
         ├──► Path 3: Security scanner ──► alerts
         └──► Path 4: DX diagnostics  ──► DevEx team
```

### Path 1: Knowledge mining (centralized)

Same extractors as the local miner, but cross-correlated across
developers. The killer feature: patterns invisible to any individual.

| Input | Cross-correlation | Output |
|---|---|---|
| Retry patterns from 5 devs | "Everyone hits EMFILE in the monorepo" | Org-wide rule: platform fix needed |
| User corrections from 3 devs | "3 people corrected the same agent mistake" | Shared rule/convention |
| Task summaries mentioning same topic | "Every new hire stumbles on fiscal year" | Onboarding skill |
| Gaps across teams | "No one knows what 'active user' means" | Glossary priority |

Output: proposed org-level artifacts → curator reviews → corp vault → all agents.

### Path 2: Analytics

Operational dashboards and reporting from trace data.

| Metric | What it tells you | Consumer |
|---|---|---|
| Tool call distribution per agent | How agents are being used | Eng management |
| Tokens per task type | Cost efficiency across teams | Finance |
| Error rate by agent × project | Which agent works best where | Platform team |
| Time-to-completion per task | Productivity trends | Eng management |
| Agent adoption by team/person | Who's using what, who isn't | CTO / DevEx |
| MCP tool usage frequency | Which integrations deliver value | Platform team |
| Sessions per developer per day | Engagement / adoption curves | DevEx |
| Skill install vs. usage rate | What's actually useful vs. shelfware | Platform team |

Output: dashboards, weekly reports, OKR tracking.

### Path 3: Security & compliance

Continuous scanning for credential exposure, policy violations, and
audit-relevant events.

| Signal | Detection method | Action |
|---|---|---|
| Secrets in prompts or outputs | Regex patterns (pre-ship + central) | Alert + rotate |
| Secrets persisted in context compaction | Scan compacted entries | Alert (secrets survive compression) |
| Prod DB accessed via agent | Tool call to prod connection string | Audit log entry |
| Unapproved MCP server appears | New server in traces not in allowlist | Flag for review |
| Large data read → paste to external | Behavioral pattern detection | Exfiltration alert |
| Agent used on unauthorized project | Session from excluded project path | Policy violation alert |

Output: security alerts, compliance reports, audit trail.

**Key finding from scanning this machine's traces:** 44 high-severity
credential exposures across 2 months — 3 unique AWS key pairs,
7 database connection strings with passwords, 4 GitHub tokens. All in
plaintext JSONL on disk, all previously sent to LLM API endpoints.
Secrets also survived context compaction (persisted in compressed
session summaries). See "Observed data" section below for full details.

### Path 4: Developer experience diagnostics

Trace patterns reveal where the developer experience is broken — not
what developers did, but what was hard.

| Signal | What it means | Action |
|---|---|---|
| Multiple devs ask agents about same topic | Documentation gap | Write the doc |
| 5 devs fought the same config this week | Broken DX | Fix the config/tooling |
| Average 3 retries before test passes | Flaky tests | Fix test infrastructure |
| Agent always reads file Y before doing Z | Implicit dependency | Make it explicit |
| New hires' sessions 3x longer for task X | Onboarding gap | Add a skill or guide |
| Same error appears across projects | Shared infrastructure issue | Platform fix |

Output: DX diagnostics for DevEx team, tech leads, onboarding program.

The EMFILE example from the observed data illustrates this path:
trace analysis revealed a monorepo file-watcher issue that wasted
multiple developers' time across weeks. This is invisible without
cross-correlation — each developer experienced it as "my dev server
is flaky," not "our platform has a file descriptor problem."

---

## Observed data: what's extractable right now

From this machine's actual traces (Mar–Apr 2026):

### Claude Code (db-mcp project, 32 sessions)

| Pattern | Estimated count | Example |
|---|---|---|
| Retries (tool fail → different input → success) | ~50-100 | pytest flags adjusted after failure |
| User corrections | ~20-30 | "that's the wrong ACP", "use commander for CLI" |
| Search gaps | ~10-15 | grep for term → no results → user explains |
| Repeated edits (3+ files) | ~15-20 | import path updates after module moves |

Tool call mix: Bash 41%, Edit 20%, Read 20%, Grep 7%, Write 5%
Token usage: ~1.4B cache reads, 1.4M generated, ~$20 est. cost

### Codex (83 sessions across 9 projects)

| Pattern | Estimated count | Example |
|---|---|---|
| Task summaries (task_complete) | ~80+ (one per completed turn) | "The design doc is strong; the impl doc is too optimistic" |
| Retries (exec_command fail → retry) | ~200+ | command variations until passing |
| MCP tool sequences | ~265 calls | validate_sql → run_sql → get_result chains |

Tool call mix: exec_command 74%, apply_patch 12%, write_stdin 11%

### Skills landscape

| Agent | Skills installed | Actively used | Stale |
|---|---|---|---|
| Claude Code | 2 project + 0 global | release (2x), update-config (1x) | playwright-cli (0x) |
| Codex | 3 global | playwright (via MCP) | pdf (unknown), playwright-interactive (unknown) |
| Codex | AGENTS.md | Active (36 references) | — |
| Codex | default.rules (76KB) | Active (permission log) | — |

### Secret exposure (scanned 236K JSONL lines, 30 seconds)

| Type | Occurrences | Unique | Severity |
|---|---|---|---|
| AWS Access Keys (AKIA...) | 5 | 3 | **HIGH** |
| AWS Secret Key | 2 | 1 | **HIGH** |
| Database URLs with passwords | 33 | 7 | **HIGH** |
| GitHub Tokens (ghp_/ghs_) | 4 | 4 | **HIGH** |
| Generic API Keys | 89 | 2 | MEDIUM |
| UUID API Keys | 97 | 4 | MEDIUM |
| OpenAI key pattern (sk-...) | 58 | 58 | LOW (likely false positives in reasoning tokens) |
| Base64 long secrets | 171 | 96 | LOW (blockchain program keys) |

**Where secrets appeared:**
- `function_call_output` (most common) — agent read .env or config files
- `user` messages — developer pasted credentials into prompts
- `reasoning` — LLM reasoned about secrets it saw (GitHub tokens)
- `compacted` — secrets **survived context compaction** and persisted
  in compressed session summaries for the rest of the session

**Actionable:** 44 high-severity findings (AWS + DB + GitHub) across
2 months of casual development use. In a 20-person org, this scales to
~400+ credential exposures per month without a secrets hygiene scanner.

---

## Relationship to other plans

| Document | Relationship |
|---|---|
| `docs/scheduler.md` | Scheduler hosts the miner daemon alongside other jobs |
| `docs/papers/managing-organizational-knowledge-in-agentic-age.md` | Miner implements Flow 1 (actions) and Flow 3 (implicit observation) |
| `docs/papers/knowledge-graph-architecture.md` | Miner output enters the knowledge DAG as signal → block transitions |
| `docs/workspaces.md` | Corp sync pushes to workspace-scoped vault |
| `packages/sigint/` | Miner extends sigint with new sources + parsers |
