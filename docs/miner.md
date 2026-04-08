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

  # Privacy controls
  privacy:
    capture_file_contents: false      # never store actual code from traces
    strip_secrets: true               # remove anything matching secret patterns
    exclude_projects: []              # project paths to skip entirely

  # Corp sync
  sync:
    enabled: false
    remote: null                      # git@github.com:acme/knowledge.git
    schedule: daily                   # daily | hourly | manual
    branch: main
```

---

## Privacy and opt-in

Miner reads local agent traces. This is sensitive data — it contains
prompts, code, reasoning, and potentially secrets.

### Principles

1. **Explicit opt-in per agent.** Each agent source must be individually
   enabled. Nothing is watched by default.
2. **Extract patterns, not content.** The output is knowledge artifacts
   (rules, decisions, patterns), not trace replays. Raw code and file
   contents are never stored in the signal store.
3. **Secret stripping.** Anything matching common secret patterns
   (API keys, tokens, passwords) is stripped before storage.
4. **Project exclusion.** Specific project paths can be excluded entirely
   (e.g., client projects under NDA).
5. **Local-first.** Traces are read locally, artifacts are stored locally.
   Corp sync is optional and pushes only approved artifacts, not raw traces.
6. **User controls the gate.** Every artifact goes through human review
   before entering the vault. No auto-apply from traces.

### What miner NEVER does

- Read traces from agents the user hasn't opted in
- Store raw code from trace tool results
- Transmit raw traces to any remote system
- Auto-apply knowledge without human review
- Access trace files from other users on shared machines

---

## Implementation phases

### Phase 1 — Claude Code trace parser + deterministic extractors

Parse Claude Code JSONL. Extract retries, corrections, and gaps.
Output to existing signal store. Review via `sigint review`.

**Files:**
- `packages/sigint/src/sources/traces.ts` — trace directory watcher
- `packages/sigint/src/parsers/claude.ts` — Claude Code JSONL parser
- `packages/sigint/src/extractors/trace.ts` — retry, correction, gap patterns

**Gate:** `sigint watch ~/dev/ --traces` detects a user correction
from a real Claude Code session and proposes it as a rule.

### Phase 2 — Codex parser + task summaries

Add Codex JSONL parsing. Extract `task_complete` summaries as ready-made
knowledge artifacts.

**Files:**
- `packages/sigint/src/parsers/codex.ts` — Codex JSONL parser

**Gate:** `sigint review` shows a Codex task completion summary
("The package split is still carrying too many shims...") as a
proposed architectural insight.

### Phase 3 — Skill monitoring

Watch skill directories, track usage from traces, detect stale skills,
suggest org promotion for heavily-used skills.

**Files:**
- `packages/sigint/src/sources/skills.ts` — skill directory watcher
- `packages/sigint/src/extractors/skill_usage.ts` — correlate with traces

**Gate:** `sigint status` shows "playwright-cli: installed, never used
(30d)" and "release: used 2x, candidate for org promotion."

### Phase 4 — Corp sync

Daily git push of approved artifacts to a corporate knowledge repository.

**Files:**
- `packages/sigint/src/sync.ts` — git push of approved artifacts

**Gate:** `sigint sync --remote git@corp/vault.git` pushes approved
rules and decisions to the org repo.

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

---

## Relationship to other plans

| Document | Relationship |
|---|---|
| `docs/scheduler.md` | Scheduler hosts the miner daemon alongside other jobs |
| `docs/papers/managing-organizational-knowledge-in-agentic-age.md` | Miner implements Flow 1 (actions) and Flow 3 (implicit observation) |
| `docs/papers/knowledge-graph-architecture.md` | Miner output enters the knowledge DAG as signal → block transitions |
| `docs/workspaces.md` | Corp sync pushes to workspace-scoped vault |
| `packages/sigint/` | Miner extends sigint with new sources + parsers |
