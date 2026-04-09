# Miner: Knowledge Extraction from Agent Traces

**Codename:** miner
**Status:** PoC implemented (agent + ingestor), design for centralized pipelines
**Date:** 2026-04-08 (design), 2026-04-08 (implementation)

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

## Authentication

### Current implementation

Two auth methods, either sufficient for accepting a batch:

| Method | Header | What it proves | Limitation |
|---|---|---|---|
| **API key** | `Authorization: Bearer key_xyz` | Caller has the key | Shared secret, no user identity |
| **Ed25519 signature** | `X-Miner-Signature` + `X-Miner-Key-Fingerprint` | This machine signed this exact payload | Machine identity only, no SSO |

Both are implemented and tested. Sufficient for development and small
teams. Not sufficient for enterprise.

### Enterprise requirements

| Requirement | Why | Current gap |
|---|---|---|
| SSO integration | Developers have Okta/Azure AD/Google identities | No IdP integration |
| No static secrets on disk | API keys in config files get leaked | API key is a static string |
| Immediate revocation | Offboarded developer loses access | API key valid until manually rotated |
| Audit trail tied to IdP | Compliance needs verified user identity | API key doesn't identify a person |
| Team/org scoping | Partition access by team membership | No team claims in auth |
| Machine attestation | Verify agent runs on managed device | Ed25519 covers this (already built) |

### Target architecture: OAuth 2.0 device flow + Ed25519

Two complementary layers:

**Layer 1 — OAuth 2.0 (user identity)**

The miner agent authenticates the developer via the org's IdP using
the OAuth 2.0 device authorization flow (RFC 8628). On first run,
`miner-agent auth login` opens a browser for SSO login. The agent
receives a short-lived JWT access token and a refresh token.

The JWT contains claims:
- `sub`: user identifier
- `email`: developer email
- `org`: organization ID
- `teams`: team memberships (for partition routing)

The ingestor validates the JWT signature against the IdP's JWKS
endpoint (`/.well-known/jwks.json`) — stateless, no per-request
IdP call.

**Layer 2 — Ed25519 (machine identity)**

The local keypair (already implemented) signs each batch body. This
proves the batch came from a specific installation and wasn't tampered
with in transit. The ingestor verifies both: valid JWT (user is
authorized) AND valid signature (batch integrity).

```
First run:
  miner-agent auth login
    → opens browser → SSO login (Okta / Azure AD / Google)
    → receives OAuth tokens → ~/.miner/auth.json (short-lived)
    → generates Ed25519 keypair → ~/.miner/miner.key (permanent)

Each batch shipped:
  POST /api/ingest
    Authorization: Bearer eyJhbG...    ← JWT from IdP
    X-Miner-Signature: base64...       ← Ed25519 over body
    X-Miner-Key-Fingerprint: a1b2...   ← machine identity
    Body: { batchId, developer, entries, ... }

Ingestor verifies:
  1. JWT valid? → check signature against IdP JWKS, check expiry
  2. User authorized? → check org claim, team membership
  3. Body intact? → verify Ed25519 signature against registered key
  4. All pass → store in developer's partition
```

**Token lifecycle:**
- Access token: 1 hour TTL, auto-refreshed by the agent
- Refresh token: 30 days, rotated on use
- Ed25519 keypair: permanent per installation, registered on first auth
- Revocation: IdP deprovisioning → refresh token invalid → agent
  can't renew → next ship fails → developer re-authenticates

**Device registration:**
On `miner-agent auth login`, the Ed25519 public key is registered with
the ingestor via an API call authenticated by the fresh OAuth token:

```
POST /api/devices/register
  Authorization: Bearer <jwt>
  Body: { publicKey: "-----BEGIN PUBLIC KEY-----...", fingerprint: "a1b2..." }
```

The ingestor stores: `{ fingerprint, publicKeyPem, developer, registeredAt }`.
Admin can revoke a device by deleting its registration.

### Ingestor auth flow (target)

```typescript
// 1. Check JWT
const jwt = await verifyJWT(authHeader, jwksCache);
if (!jwt) return 401;
if (jwt.claims.org !== config.orgId) return 403;

// 2. Check machine signature (optional — degrades gracefully)
const sigHeader = headers["x-miner-signature"];
const fpHeader = headers["x-miner-key-fingerprint"];
if (sigHeader && fpHeader) {
  const pubKey = await deviceRegistry.getKey(fpHeader);
  if (!pubKey) return 401;  // unknown device
  if (!verifySignature(body, sigHeader, pubKey)) return 403;  // tampered
}

// 3. Extract developer from JWT claims (authoritative)
const developer = jwt.claims.email;

// 4. Store
store.saveBatch({ ...batch, developer });
```

The developer identity comes from the JWT (verified by the IdP), not
from the batch body (self-reported by the agent). This prevents
impersonation.

### Implementation phases

| Phase | What | Depends on |
|---|---|---|
| **Current** | API key + Ed25519 | Done |
| **Phase 1** | OAuth device flow in agent (`miner-agent auth login`) | IdP configuration |
| **Phase 2** | JWKS validation in ingestor (stateless JWT verification) | Phase 1 |
| **Phase 3** | Team/org claims for partition routing and access control | Phase 2 |
| **Phase 4** | Device registration API (`/api/devices/register`) | Phase 2 |
| **Phase 5** | Admin UI for device management (list, revoke) | Phase 4 |

Phase 1-2 are the critical path for enterprise deployment. Phases 3-5
add governance and management capabilities.

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

## Implementation status

What has been built as of 2026-04-08:

### packages/miner/agent/ — 98 tests, all passing

| Module | Status | What it does |
|---|---|---|
| `discover.ts` | Done | Find trace dirs for Claude Code, Codex, Cursor |
| `parsers/claude.ts` | Done | Claude Code JSONL → NormalizedEntry |
| `parsers/codex.ts` | Done | Codex JSONL → NormalizedEntry (tool name mapping, task summaries) |
| `parsers/cursor.ts` | Done | Cursor SQLite (.vscdb) → NormalizedEntry (composerData + bubbleId tables) |
| `security/scanner.ts` | Done | 11 regex patterns, scan + redact (99% true positive, 5% false positive) |
| `shipper.ts` | Done | Cursor-based idempotent shipping, deterministic batchId, retry on failure |
| `http-shipper.ts` | Done | POST to ingestor with optional Ed25519 signing |
| `identity.ts` | Done | Ed25519 keypair generation, sign, verify, fingerprint |
| `config.ts` | Done | YAML config loading with defaults + merge |
| `daemon.ts` | Done | Async poll loop (discover → process → ship) |
| `cli.ts` | Done | `scan` (one-shot), `status`, `--dry-run`, `--endpoint`, `--api-key` |
| smoke tests | Done | Validated against real Claude Code + Codex traces on a live machine |

### packages/miner/ingestor/ — 23 tests, all passing

| Module | Status | What it does |
|---|---|---|
| `server.ts` | Done | HTTP server, dual auth (API key + Ed25519), batchId dedup at API level |
| `store.ts` | Done | Hive-partitioned raw zone (year/month/day/agent/dev), immutable files, append-only dedup log |
| `main.ts` | Done | CLI entry point (`--port`, `--data-dir`) |
| E2E tests | Done | Agent → HTTP → ingestor → lakehouse, verified with real data |

### Hand-tested end-to-end

```
11 Claude Code sources, 120 trace files
→ agent scans, redacts secrets, generates Ed25519 signatures
→ ships 120 batches via HTTP to local ingestor
→ 2,239 entries stored in lakehouse raw zone
→ developer auto-resolved from git config (lbeliaev@gmail.com)
```

### Learnings from implementation

**Idempotency required both sides.** The initial design had fire-and-forget
shipping — cursor advanced before confirming delivery. Fixed: `processFile()`
is now async, awaits the ship callback, and only advances cursor on success.
Ingestor deduplicates by deterministic `batchId` (SHA-256 of file + offset + size).

**Ed25519 needs `sign()/verify()`, not `createSign()/createVerify()`.** Node's
crypto module handles Ed25519 differently from RSA/ECDSA. The initial implementation
used the wrong API and failed with "Unsupported crypto operation."

**Cursor uses SQLite, not JSONL.** Discovered during implementation — Cursor stores
conversations in `.vscdb` files (SQLite key-value tables), not flat JSONL.
Required `better-sqlite3` dependency and a different parsing approach
(SQL queries over `cursorDiskKV` table, key patterns like `composerData:*`
and `bubbleId:*`).

**Vitest runs in Node, not Bun.** Several tests failed because they used
`Bun.serve()` or `Bun.file()`. All Bun-specific APIs were replaced with
Node equivalents (`http.createServer`, `fs.readFileSync`) for test compatibility.

**Parse rates are ~50%.** Claude Code: 56% of JSONL lines parse into
NormalizedEntry; Codex: 48%. The rest are system/meta entries (token_count,
context_compacted, session_meta) that don't map to user-visible actions.
These could be parsed in a future pass for the analytics pipeline.

**Flat storage doesn't scale.** The initial store wrote all batches for an
agent into one directory. At 20 devs × 50 batches/day × 30 days = 30K files
in a flat directory. Fixed: Hive-style partitioning (year/month/day/agent/dev)
with hashed developer ID for privacy and per-developer S3 isolation.

**Cross-boundary sessions need two-phase handling.** A session starting
March 31 and ending April 1 ships as one batch. Partitioning by shippedAt
keeps the write atomic. The Parquet normalization job (downstream) extracts
per-entry timestamps for accurate time-range queries.

**Dedup file must be append-only.** The initial `dedup.json` was rewritten
on every batch (read → parse → add → serialize → write). Under concurrent
writes this corrupts. Fixed: `dedup.log` is append-only (one batchId per line).

### What's NOT built yet

| Component | Status | Needed for |
|---|---|---|
| **Parquet transformation** | Not built | Analytics pipeline (Path 2) — see next section |
| **Normalization at ingest** | Not built | Cross-agent queries over unified schema |
| **Knowledge mining pipeline** | Not built | Path 1 — cross-correlated extraction |
| **Analytics dashboards** | Not built | Path 2 — usage, cost, adoption metrics |
| **Security scanning pipeline** | Not built | Path 3 — centralized secret detection |
| **DX diagnostics pipeline** | Not built | Path 4 — friction reports |
| **Cursor SQLite shipping** | Not built | Agent skips `.vscdb` files for now |
| **Config file integration** | Partial | CLI reads flags, not `~/.miner/config.yaml` |
| **Daemon watch mode** | Not built | Continuous mode (`miner-agent watch`) |

---

## Storage: JSONL → Parquet

The raw zone uses JSONL (what the agent ships). This is fine for ingestion
and debugging but inadequate for the analytics pipeline.

**Why Parquet for the normalized zone:**

| Concern | JSONL | Parquet |
|---|---|---|
| Storage | 1x (raw text) | 5-10x smaller (columnar + compression) |
| Query performance | Full scan every file | Read only needed columns |
| Schema | None — each line can differ | Typed, enforced at write |
| Ecosystem | Universal but slow to query | Native to every lakehouse tool |
| Append | Trivial | Write new files (no in-place append) |
| Human readable | Yes | No (binary) |

**Raw zone layout (implemented):**

Hive-style partitioning with developer isolation:

```
raw/
  year=2026/
    month=04/
      day=08/
        agent=claude_code/
          dev=a1b2c3d4/           ← SHA-256 prefix of developer email
            {batchId}.jsonl       ← immutable, write-once
            {batchId}.meta.json   ← batch metadata
          dev=f9e8d7c6/
            {batchId}.jsonl
        agent=codex/
          dev=a1b2c3d4/
            {batchId}.jsonl
```

**Design decisions:**

- **Developer as partition key** — enables per-developer S3 IAM policies,
  GDPR deletion (`rm -rf dev=HASH/`), and write isolation.
- **Hashed developer ID** (`dev=a1b2c3d4`) — privacy by default; the
  ingestor holds the mapping from hash to email, not the storage layer.
- **batchId as filename** — deterministic (SHA-256 of file + offset + size),
  no collision risk from concurrent writes, enables idempotent retries.
- **All files immutable** — write-once, never updated. Dedup log is
  append-only (one batchId per line, not a rewritten JSON file).
- **Partitioned by shippedAt** — the date the batch was shipped, not the
  dates of individual entries within it. This keeps batch writes atomic.

**Cross-boundary sessions:**

A session spanning midnight (or month/year boundary) ships as one batch
partitioned by `shippedAt`. The entries inside may span multiple days.
This is correct for storage (atomic writes, no splitting). The normalized
Parquet zone (below) extracts per-entry `timestamp` as a column, so
analytical queries filter on entry time, not partition date.

**Normalized zone (Parquet, not yet built):**

```
raw/ (JSONL, partitioned by ship date)
         │
    periodic batch job
    (read JSONL → parse with existing agent parsers → write Parquet)
         │
         ▼
normalized/ (Parquet, columnar, partitioned by entry date)
    sessions.parquet          — one row per session
    tool_calls.parquet        — one row per tool invocation
    messages.parquet          — one row per user/assistant message
    cost_events.parquet       — token usage + dollar cost
    secret_detections.parquet — credential exposure events
    skill_events.parquet      — skill install/invoke/retire
```

**Implementation path:** DuckDB reads the Hive-partitioned JSONL natively:

```sql
COPY (
  SELECT
    json_extract_string(line, '$.timestamp') as entry_timestamp,
    json_extract_string(line, '$.agent') as agent,
    json_extract_string(line, '$.toolName') as tool_name,
    json_extract_string(line, '$.developer') as developer
  FROM read_json_auto('raw/**/*.jsonl',
    columns={line: 'VARCHAR'}, format='newline_delimited',
    hive_partitioning=true)
) TO 'normalized/tool_calls.parquet'
  (FORMAT PARQUET, PARTITION_BY (agent, year, month));
```

DuckDB's `hive_partitioning=true` reads the `year=`, `month=`, `day=`,
`agent=`, `dev=` directory structure as virtual columns. The Parquet
output re-partitions by entry timestamp (from the JSONL content) rather
than ship date (from the directory structure).

All four pipelines (knowledge, analytics, security, DX) query the
normalized Parquet zone. They never read raw JSONL directly.

---

## Centralized architecture: Lakehouse

The local miner (Phases 1–4) handles individual developer workflows.
For organizational AI observability, a centralized lakehouse ingests
data from all sources — not just agent traces — to provide a 360-degree
view of AI's impact on the engineering organization.

### Data sources

**Tier 1 — Agent traces and local signals (already designed above)**

| Source | What it provides | Collection |
|---|---|---|
| Agent traces (local) | Reasoning chains, tool calls, outcomes | Local agent (Component 1) |
| Skill/config changes | What capabilities are available and used | File watch (local agent) |

**Tier 2 — Code and collaboration platforms**

| Source | What it provides | Collection |
|---|---|---|
| GitHub / GitLab | Commits, PRs, reviews, CI status, branch activity | Webhook or API polling |
| GitHub Copilot metrics | Acceptance rate, suggestions/day, languages, active users | Copilot Business API |
| CI/CD (GitHub Actions, Jenkins) | Build times, failure rates, deploy frequency, test results | Webhook or API |
| Jira / Linear | Tickets completed, cycle time, story points | API polling |
| Code review platforms | Review time, comments, approval rates on AI-generated PRs | GitHub API (PR metadata) |

**Tier 3 — LLM vendor APIs (Teams/Enterprise plans)**

| Source | What it provides | Collection |
|---|---|---|
| Anthropic Admin API | Per-user token usage, cost by model, rate limit consumption | API polling |
| OpenAI Admin API | Usage by user/key, cost per model, batch status | API polling |
| Cursor Business | Seats, per-user usage, feature breakdown (tab vs composer vs chat) | Admin API |
| IDE telemetry (VS Code, JetBrains) | Extensions installed, features used, editor time | Extension/plugin |

**Tier 4 — Internal tools and operational data**

| Source | What it provides | Collection |
|---|---|---|
| MCP server logs | Which MCP tools called, by whom, error rates | Server-side logging |
| Knowledge vault changes | Rules added, metrics defined, examples approved | Git history of vault |
| Incident management (PagerDuty) | Incidents caused by AI-generated code, MTTR | Webhook |
| Slack / Teams (scoped channels) | AI tool mentions, help requests, knowledge sharing | Bot or API |
| Developer surveys / NPS | Subjective satisfaction, pain points | Periodic survey |

### Trace preprocessing

Traces are preprocessed locally before shipping:

| Level | What's stripped | Recommendation |
|---|---|---|
| **Raw** | Nothing | Maximum value, maximum risk |
| **Redact secrets** | Regex-strip secrets → `[REDACTED]` | **Recommended** |
| **Strip file contents** | Remove tool_result payloads | Loses code context |
| **Metadata only** | Keep only tool names, timestamps, success/fail | Minimal value |

**Recommended:** redact secrets locally (security scanner runs BEFORE
shipping), then ship everything else.

### Lakehouse architecture

```
Developer machines (opt-in)
├── Agent traces ────────┐
├── Skill/config changes ┘── local secret scan + redaction
│                                │
│   Code & collaboration         │    LLM vendors        Internal tools
│   ├── GitHub webhooks          │    ├── Anthropic API   ├── MCP server logs
│   ├── CI/CD events             │    ├── OpenAI API      ├── Vault git history
│   ├── Jira/Linear API          │    ├── Cursor admin    ├── Incident webhooks
│   └── Copilot metrics          │    └── IDE telemetry   └── Surveys
│            │                   │           │                    │
│            ▼                   ▼           ▼                    ▼
│         ┌──────────────────────────────────────────────────────────┐
│         │  Ingestor API                                           │
│         │  (authenticate, normalize, deduplicate, store)          │
│         └──────────────────────┬───────────────────────────────────┘
│                                │
│                                ▼
│    ┌───────────────────────────────────────────────────────────────┐
│    │  Lakehouse (S3, append-only, immutable)                      │
│    │                                                              │
│    │  Raw zone (JSONL, Hive-partitioned, immutable):               │
│    │    raw/year=YYYY/month=MM/day=DD/agent=X/dev=HASH/           │
│    │      {batchId}.jsonl + {batchId}.meta.json                   │
│    │                                                              │
│    │  Non-trace sources (same partitioning):                      │
│    │    raw/.../source=github/  raw/.../source=vendor_anthropic/  │
│    │    raw/.../source=ci/     raw/.../source=jira/               │
│    │                    │                                         │
│    │              periodic batch job (DuckDB)                     │
│    │              (JSONL → parse → normalize → Parquet)           │
│    │              reads hive_partitioning=true                    │
│    │                    │                                         │
│    │  Normalized zone (Parquet, columnar, by entry timestamp):    │
│    │    sessions/         — agent sessions (cross-agent schema)   │
│    │    tool_calls/       — every tool invocation (normalized)    │
│    │    commits/          — git commits with AI-attribution flag  │
│    │    pull_requests/    — PRs with AI-contribution metadata     │
│    │    cost_events/      — token usage + $ per session/user      │
│    │    tickets/          — Jira/Linear with AI-assist flag       │
│    │    ci_runs/          — builds linked to commits              │
│    │    secret_detections/— credential exposure events            │
│    │    skill_events/     — install, invoke, promote, retire      │
│    │    knowledge_events/ — vault writes, approvals, dismissals   │
│    │                                                              │
│    │  Curated zone:                                               │
│    │    knowledge_artifacts/   analytics_aggregates/              │
│    │    security_findings/     dx_diagnostics/                    │
│    └───────────────────────────┬───────────────────────────────────┘
│                                │
│         ┌──────────┬───────────┼───────────┬──────────┐
│         ▼          ▼           ▼           ▼          ▼
│    Knowledge    Analytics   Security      DX      AI Leader
│    miner        engine      scanner    diagnostics  360° view
│       │            │           │           │
│       ▼            ▼           ▼           ▼
│    Corp vault   Dashboards  Alerts     DevEx reports
│    (git)        (Grafana)   (Slack)    (weekly)
```

### Enrichment joins

The real value is cross-referencing data sources:

| Join | What it reveals |
|---|---|
| Agent trace × Git commit (by timestamp + project) | "This commit was produced by an AI agent" |
| Vendor cost × Git output (by user + time) | Cost per PR, cost per feature, cost per bug fix |
| Agent trace × Jira ticket (by branch + time) | Ticket closed with AI assistance — velocity impact |
| Agent retries × CI failures (by project) | "Agent struggled because tests are flaky" (infra, not AI) |
| Skill usage × Developer role/tenure | Seniors use different skills than juniors |
| MCP tool calls × Query results | Which db-mcp queries produce value vs. waste tokens |
| Secret exposure × Developer × Project | Which workflows lack secrets management |
| PR review time × AI-authored flag | Are AI-generated PRs reviewed faster or slower? |
| Copilot acceptance rate × Agent trace volume | Do active agent users also accept more Copilot suggestions? |
| Incident × AI-authored commit (by deploy) | Did AI-generated code cause production incidents? |
| New hire session patterns × tenure | Onboarding friction visible from trace length/retries |

### Questions the 360° view answers

| Question | Data sources needed |
|---|---|
| "How much are we spending on AI?" | Vendor APIs (cost) + seat licenses |
| "Is it worth it?" | Vendor cost + Jira velocity + CI build times (before/after) |
| "Who's using AI and who isn't?" | Vendor APIs (per-user) + traces (sessions/dev) |
| "What are they using it for?" | Traces (tool calls, task types) |
| "Is AI-generated code good?" | GitHub (PR reviews, revert rate) + CI (test pass rate) |
| "Are we exposed?" | Secret scanner + traces (data access patterns) |
| "What knowledge are we building?" | Vault changes + knowledge miner output |
| "Where is AI struggling?" | Traces (retries, errors) + DX diagnostics |
| "What should we invest in next?" | Skill usage + gap signals + DX friction |
| "Did AI code break production?" | Incidents × AI-authored commits × deploys |
| "Are we compliant?" | Security scanner + audit trail |

### What's missing (known gaps)

**1. Cost attribution.** Vendor APIs give total cost per user. But
attributing cost to a specific project, feature, or Jira ticket
requires joining vendor usage with git/Jira data by timestamp and
user. If the org uses one API key per team, attribution is easy. If
one key for everyone, trace-level data (which includes session →
project mapping) is the only way.

**2. Production quality signal.** All the data above measures the
development process. Missing: did the AI-generated code work in
production? Requires linking: commit → deploy → production metrics
(error rates, latency, incidents). The incident management source
partially covers this, but proactive quality metrics (error rate per
AI-authored vs human-authored code) require deeper production
observability integration.

**3. Pre-AI baseline.** "AI saves time" requires knowing how long
things took before. If the org adopts AI tools and the lakehouse
simultaneously, there is no baseline. Recommendation: start collecting
git, Jira, and CI data NOW, even before agent-specific sources, to
establish pre-AI velocity and quality metrics.

**4. The human side.** Developer satisfaction, cognitive load, skill
atrophy ("are developers losing the ability to code without AI?"),
trust calibration ("do developers over-trust AI output?"). Surveys
are the only source. They are noisy but irreplaceable — no amount of
trace data tells you whether people are happy or growing.

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
