# Knowledge Layer as a Merkle DAG

*Content-addressable, provenance-native, selectively disclosable
organizational knowledge.*

---

## Motivation

The knowledge layer (KL) is the central artifact in the db-mcp
architecture. Two products interact with it: db-mcp (query/operations)
reads KL for context and writes execution signals back; db-sig
(signals/curation) ingests from external systems and enriches KL
through human-in-the-loop curation.

The current vault is files on disk — YAML documents in a directory tree,
version-controlled with git. This works for storage but doesn't answer
fundamental questions:

- **Why does this rule exist?** No causal link from knowledge to its
  origin signal.
- **How has it changed?** Git log gives diffs, but not the causal chain
  (which signal triggered which change).
- **Is it still valid?** No structural way to trace from a rule to the
  executions that validated it.
- **Can I share this without sharing everything?** No selective
  disclosure — you share the whole vault or nothing.

These aren't logging problems. They're structural. The knowledge layer
needs provenance, history, and verifiability as inherent properties,
not bolted-on metadata.

---

## Core idea: knowledge as a content-addressable graph

Every piece of knowledge — a rule, a metric, a schema description, a
signal, a curation decision — is a **node** in a directed acyclic graph.
Each node is identified by the hash of its content. Links between nodes
are also hashes. The graph structure IS the provenance.

This is the same structure that makes Git (commits → trees → blobs),
IPFS (content-addressed blocks with IPLD links), and blockchains
(transactions → Merkle roots) work. Applied to organizational knowledge,
it provides:

| Property | How the DAG provides it |
|---|---|
| **Identity** | Hash of content. Same content = same hash. Always. |
| **Immutability** | Updates create new nodes that reference parents. Old nodes persist. |
| **Provenance** | Links from knowledge → source signals → curation events. The graph IS the audit trail. |
| **Verifiability** | Walk the DAG from any node back to its origins. Every link is verifiable. |
| **Selective disclosure** | Reference a node by hash without revealing content. Need-to-know resolution. |
| **History** | Parent links form a version chain. No separate changelog needed. |

---

## The Block: unit of knowledge

A **block** is a concept, component, feature, or decision that has
identity across time. It is the primary node type in the knowledge
graph. A block is not a file — it is the *thing* that files describe.
"TUI" is a block whether it was planned in Python or built in
TypeScript. The block persists; its state, content, and artifacts
change.

### Block types

| Type | What it represents | Example |
|---|---|---|
| `component` | A system or module | TUI, CLI, gateway, sigint |
| `feature` | A specific capability | UNION validation, JSON-RPC auth |
| `design` | An architectural concept | Knowledge pipeline, dual-format vault |
| `decision` | A choice with rationale | "Vendor ACP bridge instead of npm" |
| `convention` | A recurring practice | "One file per rule, YAML for schema" |
| `rule` | A constraint to follow | "Exclude test accounts from DAU" |
| `metric` | A measured quantity | DAU, revenue, churn |

### Block structure

Every block is a markdown file with YAML frontmatter:

```markdown
---
id: tui
type: component
title: Terminal UI
status: active
created: 2026-03-01
supersedes: null
superseded_by: null
---

# Terminal UI

Real-time event feed for db-mcp, styled after Claude Code's output.

## Artifacts
- Design: [[docs/tui-design.md]]
- Code: [[packages/terminal/src/index.ts]]

## Depends on
- [[block/acp-integration]]
- [[block/daemon]]

## History

- **2026-03-01** ○ → idea
  [[docs/tui-design.md]] created. Concept: Textual (Python) feed.

- **2026-03-15** idea → planned
  [[docs/tui-implementation.md]] written. 4 phases.

- **2026-04-01** planned → active
  PR #83. Built in TypeScript, not Python.

- **2026-04-06** active (drift detected)
  sigint: tui-implementation.md references Python paths.
```

The **frontmatter** is structured data (queryable, filterable). The
**body** is linked prose (navigable by humans and agents). The
**history** section is the temporal record — an ordered list of state
transitions with evidence.

### State machine

Every block follows a finite state machine:

```
          propose
    ○ ──────────► idea
                   │
            plan   │  dismiss
           ┌───────┤──────────► dismissed
           ▼       │
         planned   │
           │       │
    implement      │
           │       │
           ▼       │
        active ────┤
           │       │  supersede
      drift/stale  │──────────► superseded
           │       │                │
           ▼       │         archive│
         stale     │                ▼
           │       │            archived
    revive │       │
           └───────┘
```

| State | Meaning |
|---|---|
| `idea` | Discussed or proposed, no formal plan |
| `planned` | Has a design doc or explicit plan |
| `active` | Implemented and in use |
| `stale` | Implemented but docs have drifted, or not validated recently |
| `superseded` | Replaced by another block |
| `dismissed` | Considered and explicitly rejected |
| `archived` | Retired, kept for historical reference |

### Transitions

Each state change is a **transition** — the atomic unit of temporal
knowledge. A transition records:

```
- **{date}** {from_state} → {to_state}
  By: {actor}. Evidence: [[{artifact}]]
  Note: {optional context}
```

Transitions are **immutable** and **append-only**. You never edit a
past transition — you add a new one. This gives every block a complete,
auditable history that answers: "How did this concept evolve? Who
decided what, when, and based on what evidence?"

Transitions can be:
- **Explicit** — a human or agent changes state deliberately
  ("I'm implementing this now")
- **Detected** — sigint or a scheduler notices a drift
  ("docs reference code paths that no longer exist")
- **Inferred** — the agent reads git history and reconstructs
  what happened ("PR #83 created packages/terminal/, implementing
  the TUI block")

### Graph edges from blocks

Blocks link to other blocks and to artifacts:

| Link type | Meaning | Example |
|---|---|---|
| `[[block/X]]` in Depends on | This block requires X | TUI depends on ACP integration |
| `[[block/X]]` in superseded_by | X replaced this block | Python TUI → TypeScript TUI |
| `[[docs/X]]` in Artifacts | Design document for this block | tui-design.md |
| `[[packages/X]]` in Artifacts | Implementation code | packages/terminal/ |
| `[[signals/X]]` in History | Signal that triggered a transition | sigint detected drift |

These links form the graph. The block's state machine provides the
temporal dimension. Together: a navigable, time-aware knowledge graph
where you can ask "what is the current state of X?" AND "how did X
get here?"

---

## Supporting node types

Beyond blocks, the graph contains supporting nodes for signals,
curation events, and execution records:

### Node envelope

All nodes share a common structure:

```
KnowledgeNode:
  hash: bytes32                        # SHA-256 of canonical(type + content + links)
  type: block | signal | curation | execution
  content: structured + freeform       # typed payload + markdown

  # Graph edges
  parents: [hash]                      # previous versions (version chain)
  links:                               # typed edges to other nodes
    derived_from: [hash]               # source signals
    corroborated_by: [hash]            # execution outcomes
    approved_by: hash                  # curation event
    supersedes: hash                   # what this replaces
    conflicts_with: [hash]             # known contradictions
    depends_on: [hash]                 # prerequisite knowledge
    scoped_to: [hash]                  # connection/group scoping

  # Metadata (mutable, not part of hash)
  state: <FSM state>
  created_at: timestamp
  resolved_by: identity
```

For block nodes, the `state` field follows the FSM defined above.
For signal nodes, state is `pending | processed | expired`.
For curation nodes, state is the decision: `approved | dismissed`.

---

## Node types

### Knowledge nodes (the "stones" in the vault)

**Rule**
```yaml
hash: bafk...r1
type: rule
content:
  rule: "Active users: exclude rows where is_test = true"
  scope: ["prod-postgres"]
  entities: ["users.is_test"]
  description: |
    Test accounts are created by QA and engineering for integration
    testing. Including them inflates DAU by ~10x. This filter should
    be applied to any query counting or listing "active users."
links:
  derived_from: [bafk...sig1]
  corroborated_by: [bafk...exec1, bafk...exec2]
  approved_by: bafk...cur1
```

**Metric**
```yaml
hash: bafk...m1
type: metric
content:
  name: "daily_active_users"
  sql: "COUNT(DISTINCT user_id) WHERE last_active >= CURRENT_DATE - 1"
  dimensions: ["region", "platform"]
  description: |
    Unique users who performed at least one action in the past 24 hours.
    Excludes test accounts per rule bafk...r1.
links:
  depends_on: [bafk...r1]
  derived_from: [bafk...sig3]
  approved_by: bafk...cur2
```

**Description**
```yaml
hash: bafk...d1
type: description
content:
  table: "orders"
  column: "discount_type"
  description: |
    Type of discount applied to the order. Values: "percentage",
    "fixed_amount", "coupon", null (no discount).
links:
  derived_from: [bafk...sig_github1]
  approved_by: bafk...cur3
```

**Example**
```yaml
hash: bafk...e1
type: example
content:
  intent: "monthly revenue by region"
  sql: "SELECT region, SUM(amount) FROM orders WHERE..."
  connection: "prod-postgres"
links:
  depends_on: [bafk...r1, bafk...m2]
  corroborated_by: [bafk...exec5]
  approved_by: bafk...cur4
```

### Signal nodes (pipeline inputs)

**Signal from Slack**
```yaml
hash: bafk...sig1
type: signal
content:
  source: "slack:#data-eng"
  source_ref: "msg_20240315_xyz"
  author: "@sarah (Senior Data Engineer)"
  raw: "active users shouldn't include anyone with is_test=true,
        we've been overcounting DAU for months"
  extracted_entities: ["users.is_test"]
  category: "rule_candidate"
links:
  produced: [bafk...r1]
```

**Signal from GitHub**
```yaml
hash: bafk...sig_github1
type: signal
content:
  source: "github:apelogic/analytics"
  source_ref: "PR #1234, file: migrations/003_add_discount.sql"
  raw: "ALTER TABLE orders ADD COLUMN discount_type VARCHAR(20);"
  category: "schema_change"
links:
  produced: [bafk...d1]
```

**Signal from query execution**
```yaml
hash: bafk...exec1
type: execution
content:
  query_id: "q_abc123"
  connection: "prod-postgres"
  sql: "SELECT COUNT(DISTINCT user_id) FROM users WHERE is_test = false"
  rows_returned: 1247
  duration_ms: 38
  outcome: "success"
links:
  corroborates: [bafk...r1]
  used_knowledge: [bafk...r1, bafk...m1]
```

### Curation nodes (human-in-the-loop decisions)

```yaml
hash: bafk...cur1
type: curation
content:
  action: "approved"
  curator: "user:jane"
  comment: "Confirmed with Sarah. Applies to all environments."
  disposition_reasons:
    - "Source is a senior data engineer in #data-eng"
    - "Entity match: exact (users.is_test column exists)"
    - "Corroborated by 3 queries that already filter on is_test"
    - "No conflicts with existing rules"
  evidence_reviewed: [bafk...sig1, bafk...exec1]
links:
  approves: bafk...r1
```

---

## Graph traversals

The graph structure makes common questions into traversals:

### "Why does this rule exist?"

Start at the rule node, follow `derived_from` links to source signals,
follow `approved_by` to the curation event.

```
bafk...r1 (rule: exclude is_test)
  ← derived_from: bafk...sig1 (Slack: Sarah said exclude test accounts)
  ← corroborated_by: bafk...exec1 (query returned expected 1,247 rows)
  ← approved_by: bafk...cur1 (Jane approved, reviewed signal + execution)
```

### "What changed and why?"

Follow the `parents` chain. Each version links to the signal that
triggered the change.

```
bafk...r1_v2 (rule: exclude is_test AND is_internal)
  ← parents: bafk...r1_v1 (original: is_test only)
  ← derived_from: bafk...sig_gh2 (GitHub PR#456 added is_internal)
  ← approved_by: bafk...cur5 (Bob approved)
```

### "Is this rule still valid?"

Follow `corroborated_by` links to execution nodes. Check recency.

```
bafk...r1 → corroborated_by:
  bafk...exec1 (2024-03-20, 1,247 rows, success)
  bafk...exec2 (2024-06-15, 1,312 rows, success)
  bafk...exec3 (2024-09-15, 1,301 rows, success)  ← most recent
  → last validated 6 months ago → stale?
```

### "What knowledge did this signal produce?"

Follow `produced` links from a signal node.

```
bafk...sig1 (Slack message) → produced:
  bafk...r1 (active users rule)
  bafk...m1 (DAU metric, partially derived)
```

### "What breaks if I change this table?"

Find all knowledge nodes with `entities` referencing the table.
Follow `depends_on` links to find transitive dependencies.

```
Change: drop column users.is_test
  → bafk...r1 (rule referencing users.is_test)
    → bafk...m1 (metric depending on rule r1)
      → bafk...e1 (example depending on metric m1)
  Impact: 1 rule, 1 metric, 1 example affected
```

---

## Selective disclosure

A node can be referenced by hash without revealing its content. This
enables access-controlled knowledge in a shared graph.

### How it works

Every node has a `resolved_by` field indicating who can read its content.
The hash is always public — the content is conditionally accessible.

```yaml
hash: bafk...rule_compensation
type: rule
content: ENCRYPTED(key=hr_knowledge_key)
  # Decrypted content only visible to HR and Finance agents
resolved_by: ["role:hr", "role:finance", "user:cfo"]
links:
  derived_from: [bafk...sig_hr_policy]      # also confidential
  approved_by: bafk...cur_cfo               # also confidential
  scoped_to: [bafk...conn_hr_postgres]
```

### What agents see without access

An agent querying prod-postgres encounters a link to
`bafk...rule_compensation`:

- It knows a rule exists that affects compensation queries
- It knows the rule was approved (curation node exists)
- It cannot read the rule content
- It can report: "A confidential rule applies to this table.
  Request access from HR to proceed."

### What agents see with access

The hash resolves to the decrypted content. The agent applies the rule
normally. The access grant is itself a node in the graph (auditable).

### Cross-org sharing

Organization A can share its graph structure with Organization B:

- B sees which topics A has knowledge about (table names, metric names)
- B cannot read the actual rules, descriptions, or examples
- If A grants access to specific nodes, B can verify their integrity
  (hash matches content)
- B can link its own knowledge to A's nodes: "our metric depends on
  their definition of `bafk...m1`"

This enables knowledge marketplaces: an analytics consultancy publishes
a graph of metric definitions. Clients link to them. Updates propagate
through hash references.

---

## Relationship to the current vault

### Workspace-aware structure

The vault organizes knowledge across four levels (see `workspaces.md`):

```
~/.db-mcp/
├── index.md                           ← vault root, links to all levels
├── me/                                ← personal (sigint signals + curated)
│   ├── rules/
│   ├── patterns/
│   └── decisions/
├── global/                            ← org-wide (git-synced)
│   ├── rules/
│   ├── glossary/
│   └── metrics/
├── workspaces/{name}/                 ← team-scoped (git-synced per workspace)
│   ├── workspace.yaml
│   ├── rules/
│   ├── metrics/
│   └── connections/{conn}/            ← connection-specific
│       ├── schema/descriptions.yaml   ← YAML (systems consume)
│       ├── rules/*.md                 ← markdown (agents/humans consume)
│       ├── metrics/*.md               ← markdown + YAML frontmatter
│       ├── examples/*.md
│       ├── vault-view/schema/*.md     ← generated from YAML (read-only)
│       └── index.md                   ← generated (links to everything)
└── connections/                       ← legacy flat (backward compat)
```

### Dual-format principle

**Linked markdown** for prose knowledge consumed by agents and humans:
rules, patterns, decisions, glossary entries. One file per entry, with
`[[wiki links]]` between related entries. Navigable in Obsidian and
by any agent that can read files.

**Structured YAML** for data consumed by systems deterministically:
schema descriptions, metric SQL, domain models, connector configs.
Parsed in bulk by query engines. Not interpreted as prose.

For YAML that also needs to be navigable, **generated markdown views**
provide the bridge. These are read-only files with a `generated: true`
frontmatter marker, regenerated on vault changes.

### Migration path

**Phase 1 — Linked markdown for new entries**

New rules, patterns, and decisions from sigint's curation flow are
written as markdown files with `[[links]]`. Existing YAML vault
continues to work. Generated `index.md` files bridge the two.

```markdown
<!-- rules/active-users-filter.md -->
# Active Users Filter

Exclude test accounts: `WHERE is_test = false`

## Applies to
- [[schema/users#is_test]]

## Used by
- [[metrics/dau]]

## Source
- [[signals/slack-sarah-2024-03-15]]
- Approved by: Jane, 2024-03-17
```

The `[[links]]` ARE the graph edges. No separate `_links` metadata
needed — the links live in the content, parseable by both Obsidian
and agents.

**Phase 2 — Git-native provenance**

Structured commit trailers track causal links (see "Alternative:
Git-native architecture" section below):

```
Add rule: active-users-filter

Derived-From: signal:slack:msg_20240315
Corroborated-By: execution:exec_abc123
Approved-By: user:jane
```

**Phase 3 — Generated views for YAML content**

```yaml
# schema/descriptions.yaml stays as-is
```

```markdown
<!-- vault-view/schema/users.md — generated, DO NOT EDIT -->
---
generated: true
source: schema/descriptions.yaml
---
# users
| Column | Type | Description | Referenced by |
|---|---|---|---|
| is_test | boolean | Test account flag | [[rules/active-users-filter]] |
```

**Phase 4 — DAG index (when needed)**

Add SQLite index for fast graph traversals when the vault exceeds
~500 entries. The index is derived from markdown links + git history,
rebuildable, not a separate source of truth.

### Legacy migration

Existing `business_rules.yaml` with all rules in one file migrates to
one `.md` per rule. Existing `catalog.yaml` migrates to one `.md` per
metric with YAML frontmatter. `descriptions.yaml` stays YAML with a
generated markdown view. The migration is incremental — both formats
coexist during transition.
```

Hashes are computed on write and verified on read. Broken hashes
(manual edit changed content without updating hash) trigger a
re-hash with a `manual_edit` signal node.

**Phase 2 — DAG index**

Add a local index (SQLite) that makes graph traversals fast. The
YAML files remain the source of truth; the index is derived and
rebuildable.

```sql
CREATE TABLE nodes (hash TEXT PRIMARY KEY, type TEXT, content_path TEXT);
CREATE TABLE edges (source_hash TEXT, edge_type TEXT, target_hash TEXT);
CREATE INDEX idx_edges_target ON edges(target_hash);
```

This enables: "what knowledge came from GitHub signals?" or "what
depends on this table?" without scanning every YAML file.

**Phase 3 — Content-addressable store**

Optional: move to a CAS (content-addressable store) where nodes are
immutable blobs. The YAML vault becomes a "working tree" view
materialized from the DAG head.

Options:
- **Bare git objects** — the simplest CAS, already available
- **Local CAS** — directory of `{hash}.yaml` files
- **IPFS** — for cross-org sharing and decentralized resolution
- **Custom store** — SQLite blob table with hash keys

The vault files are generated from the graph rather than being the
source of truth. This inverts the authority: the DAG is canonical,
the files are a view.

---

## Alternative: Git-native architecture

The phased migration above builds a custom DAG on top of git. An
alternative is to lean into git itself as the graph engine, since git's
core data model — commits with N parents pointing to trees of blobs — is
already a Merkle DAG.

### What git provides natively

| DAG need | Git primitive | Fit |
|---|---|---|
| Content-addressable identity | SHA-1/SHA-256 object hash | Exact |
| Immutable history | Commits are append-only | Exact |
| Version chain (single parent) | Commit parent | Exact |
| Multiple parents | Merge commit (N parents, native) | Exact |
| Diffing any two versions | `git diff` | Excellent |
| Line-level attribution | `git blame` | Good |
| Branching / parallel work | Branches | Excellent |
| Distributed replication | Clone, push, pull | Excellent |
| Rollback | `git revert` | Excellent |

Git merge commits natively support the multi-parent case that arises
frequently in knowledge curation:

```
Signal A (Slack: "exclude test accounts")
    │
    ▼
branch: draft/exclude-test
    add rule: is_test = false
    │
    │   Signal B (Jira: "active means 30 days")
    │       │
    │       ▼
    │   branch: draft/30-day-window
    │       add rule: last_active >= now() - 30d
    │       │
    └───────┤
            ▼
      merge commit (2 parents)
        combined rule: is_test = false AND last_active >= 30d
            │
            ▼
      curation commit
        curator approves, adds provenance trailer
```

`git log --graph` shows the diamond. `git blame` traces each line to
its origin branch. `git log --merges` finds all knowledge entries with
multiple parents.

### Structured commit trailers as links

Git commit trailers (RFC 822-style key-value pairs at the end of commit
messages) provide typed links without any custom metadata format:

```
Add rule: active_users_exclude_test

Active users must exclude test accounts (is_test = true) and
must have been active within the last 30 days.

Derived-From: signal:slack:msg_20240315_xyz
Derived-From: signal:jira:TICKET-456
Corroborated-By: execution:exec_abc123
Corroborated-By: execution:exec_def456
Approved-By: user:jane
Scope: connection:prod-postgres
Entities: users.is_test, users.last_active
```

Trailers are machine-parseable with `git log --format='%(trailers)'`.
They compose with standard git tooling — no custom storage layer.

### One file per knowledge entry

For entry-level granularity (not file-level), use one file per entry:

```
vault/
├── rules/
│   ├── active-users-exclude-test.yaml
│   ├── fiscal-year-boundary.yaml
│   └── ...
├── metrics/
│   ├── daily-active-users.yaml
│   └── monthly-revenue.yaml
├── descriptions/
│   ├── orders.discount_type.yaml
│   └── ...
├── examples/
│   ├── monthly-revenue-by-region.yaml
│   └── ...
└── signals/
    ├── 2024-03-15-slack-test-accounts.yaml
    └── ...
```

Each file is a single knowledge entry. Git blame operates per-file
(showing the full provenance of that entry). Commits touch only the
files they affect. Branch-per-entry is possible but not required —
the commit trailers carry the logical lineage.

### What git does NOT give you

**Typed graph traversal.** "What depends on this column?" requires
`grep` across all YAML files, not an indexed lookup. For a small vault
(hundreds of entries), this is fast enough. For enterprise scale
(thousands), it becomes a bottleneck.

**Efficient reverse lookups.** "Which signals produced this rule?"
requires scanning commit history for trailers referencing the rule's
file. `git log -- vault/rules/active-users-exclude-test.yaml` gives
the commit history, but extracting `Derived-From` trailers across
many commits is `O(commits)`.

**Selective disclosure.** Git is all-or-nothing at the repo level.
You cannot share some entries while hiding others in the same repo.
Multi-repo structures or git submodules approximate this but fragment
the graph.

**Operational state queries.** "List all stale rules" requires reading
every rule file and checking corroboration recency. Git doesn't index
content — it versions it.

**Cross-repo links.** If knowledge spans multiple repos (different
access levels, different teams), links between them are strings, not
verified hash references. Git doesn't resolve cross-repo object
references.

### When to add an index

The git-native approach works without any index until one of these
triggers hits:

| Trigger | Symptom | Solution |
|---|---|---|
| > 500 knowledge entries | `grep` across YAML is slow | SQLite index over files |
| Frequent "what depends on X?" queries | Full-repo scan per query | Edge table with reverse index |
| Signal volume > 100/day | Commit history scanning for trailers is slow | Trailer index table |
| Cross-team access control needed | Can't share partial repo | Separate repos + cross-repo link resolution |

The index is always **derived from git** — rebuildable from
`git log` + file contents. Git remains the source of truth.

### Comparison: custom DAG vs. git-native

| Dimension | Custom DAG (Phases 1-3) | Git-native |
|---|---|---|
| Storage | YAML + optional CAS | Git repo (already exists) |
| Identity | Custom hash in `_hash` field | Git object SHA |
| Links | `_links` fields in YAML | Commit trailers |
| Multi-parent | `_parents: [hash, hash]` | Merge commit (native) |
| History | `_parents` chain | `git log` |
| Traversal | SQLite index (Phase 2) | `grep` + `git log` (add index when slow) |
| Tooling | Custom read/write logic | Standard git CLI + any git client |
| Selective disclosure | Encrypted content field | Multi-repo (fragmented) |
| Cross-org sharing | IPFS / CAS (Phase 3) | Git remotes / forks |
| Human readability | YAML with metadata noise | Clean YAML + trailers in commits |
| Barrier to entry | Custom tooling required | `git log`, `git blame`, `grep` |

### Recommendation

**Start git-native.** One file per entry, structured commit trailers
for links, merge commits for multi-parent knowledge. This works today
with zero new infrastructure, composes with existing git tooling, and
keeps the vault human-readable without `_hash` / `_links` clutter in
every YAML file.

**Add a derived SQLite index** when graph queries become frequent or
the vault exceeds ~500 entries. The index reads git history + file
contents, builds an edge table, and serves traversal queries. Git
remains the authority; the index is a cache.

**Graduate to the custom DAG** (Phases 2-3 of the original architecture)
only when selective disclosure or cross-org sharing become real
requirements. At that point, the git history provides a migration
source — every commit trailer maps to a DAG link, every merge commit
maps to a multi-parent node.

The two approaches are not competing architectures — they are points
on a continuum. Git-native is the starting position. The custom DAG
is the destination if enterprise requirements demand it. The index is
the bridge between them.

---

## Product architecture with the graph

```
                    ┌──────────────────────┐
                    │    External Systems   │
                    │  GitHub, Slack, Jira  │
                    │  dbt, Salesforce, ... │
                    └──────────┬───────────┘
                               │ events
                               ▼
┌─────────────────────────────────────────────────┐
│  db-sig (signal processing + curation)          │
│                                                 │
│  Adapters → Extraction → Interpretation         │
│                              ↓                  │
│                    Signal Nodes (bafk...sig)     │
│                              ↓                  │
│                    Disambiguation                │
│                              ↓                  │
│                    Proposed Knowledge Nodes      │
│                              ↓                  │
│              Human-in-the-Loop Curation          │
│                              ↓                  │
│                    Curation Nodes (bafk...cur)   │
└──────────────────────┬──────────────────────────┘
                       │ writes nodes + links
                       ▼
          ┌────────────────────────┐
          │     Knowledge DAG      │
          │                        │
          │  Rule ← Signal         │
          │    ↑       ↑           │
          │  Metric  Curation      │
          │    ↑                   │
          │  Example ← Execution   │
          │                        │
          │  (content-addressable, │
          │   immutable,           │
          │   selectively          │
          │   disclosable)         │
          └────────────┬───────────┘
                       │ reads nodes + writes execution signals
                       ▼
┌─────────────────────────────────────────────────┐
│  db-mcp (query + operations)                    │
│                                                 │
│  Agent → Query Intent                           │
│           ↓                                     │
│  Read active knowledge (traverse DAG head)      │
│           ↓                                     │
│  Generate SQL → Validate → Execute              │
│           ↓                                     │
│  Execution Node (bafk...exec)                   │
│  → corroborates or contradicts knowledge nodes  │
└─────────────────────────────────────────────────┘
```

---

## The temporal dimension

Most knowledge systems capture a snapshot — what knowledge looks like
now. They have no concept of time, history, or causality. This is a
fundamental limitation: a business rule without provenance is an
assertion. A rule with its full history — when it was proposed, what
signal triggered it, who approved it, what executions corroborated it,
when it drifted — is evidence.

### Time in the graph

The block's FSM and its transition history provide the temporal
dimension. Instead of asking "what do we know?" (snapshot), you can
ask:

- **"How did this rule come to exist?"** — follow the History section
  backward through transitions to the originating signal
- **"When did our understanding change?"** — look for transitions
  where a block's state changed from active to stale, or where it
  was superseded
- **"What was our knowledge at time T?"** — filter transitions to
  those before T, reconstruct the state each block was in
- **"What caused this change?"** — each transition links to evidence
  (a signal, a commit, a curation decision)

### Evolution chains

Some concepts evolve through multiple blocks over time:

```
vault format:
  YAML vault (2026-02, active → superseded)
    → linked markdown (2026-04-06, idea → planned)
      → dual-format vault (2026-04-08, idea, current)

TUI stack:
  Python/Textual TUI (2026-03-01, planned → dismissed)
    → TypeScript TUI (2026-04-01, active, current)
```

Each arrow is a `superseded_by` link between blocks. The chain
shows how organizational thinking evolved — not just what the
current answer is, but the path that led there. This is the
institutional memory that traditionally exists only in people's heads.

### Staleness as a temporal property

A block becomes stale not when someone marks it, but when temporal
evidence accumulates:

- **Doc drift:** the block's artifact links point to docs that
  reference code paths that have moved or been deleted
- **Validation gap:** no corroborating execution signals within
  the block's expected validation interval
- **Dependency drift:** a block this one depends on has been
  superseded, but this block hasn't been updated
- **Contradiction:** a new signal conflicts with this block's
  content

Staleness detection is a graph traversal + temporal check: for each
active block, verify that its evidence chain is recent and its
dependencies are still active. This is what the scheduler's "lint"
job does — the temporal equivalent of a health check.

### Recovering knowledge from history

When an organization needs to understand past decisions — why a
metric was defined a certain way, why an approach was abandoned —
the temporal graph provides the answer without archaeology. Instead
of reading through git blame and Slack archives, the agent reads the
block's history section and follows the evidence links.

This is particularly valuable for:
- **Onboarding:** new team members see not just current knowledge
  but how it got there and why alternatives were rejected
- **Incident review:** when something breaks, trace back through
  the knowledge that informed the decision
- **Audit:** demonstrate that a rule was proposed, reviewed, and
  approved through a documented process

---

## Open design questions

**1. Hash algorithm.** SHA-256 is sufficient for integrity. If
cross-org sharing or content-addressing at scale is needed, consider
CID (Content Identifier) format from IPFS for self-describing hashes.

**2. Canonical serialization.** Hashing requires deterministic
serialization. YAML is not canonical (key ordering, whitespace).
Options: sort keys + strip whitespace, use JSON for hash input, or
define a canonical form.

**3. Graph storage.** Phase 1 (YAML metadata) has no storage
overhead. Phase 2 (SQLite index) adds a derived store. Phase 3
(CAS) replaces the file-based vault. The transition should be
non-breaking — each phase is additive.

**4. Working tree materialization.** When the DAG is the source of
truth (Phase 3), how is the "current active knowledge" materialized
for agent consumption? Likely: a view that collects all nodes with
`state: active` and no `supersedes` successors — the DAG head.

**5. Garbage collection.** Immutable nodes accumulate. Old signal
nodes, superseded knowledge versions, expired proposals. A GC policy
is needed: retain all curation and knowledge nodes forever (audit
trail), GC signal and execution nodes after configurable TTL.

**6. Conflict resolution protocol.** When two signals produce
contradictory knowledge updates, the graph records both and links
them with `conflicts_with`. But what's the resolution workflow?
Options: curator picks one, merge into a new node that references
both, or scope-split (both are correct in different contexts).

**7. Trust anchors.** In a cross-org graph, which nodes do you trust?
A trust anchor is a set of curator identities or organizational roots
whose approval you accept. Nodes approved by untrusted curators are
visible but treated as unverified.

---

## Relationship to other plans

| Document | Relationship |
|---|---|
| `knowledge-pipeline.md` | The pipeline produces signal and execution nodes that enter the graph |
| `scheduler.md` | Scheduled jobs produce signal nodes (schema_drift, staleness, etc.) |
| `signal-processing-pipeline` (in paper) | The five-stage pipeline maps to: extraction → signal node → interpretation links → curation node → active knowledge node |
| `managing-organizational-knowledge-in-agentic-age.md` | This architecture implements the knowledge layer described in the paper |
| `tui-implementation.md` | TUI surfaces proposed nodes for curation (/confirm, /dismiss) |
| `vault-write-unification.md` | Schema registry becomes the write gate for DAG node creation |
