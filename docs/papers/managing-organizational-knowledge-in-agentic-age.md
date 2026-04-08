# Managing Organizational Knowledge in the Agentic Age

*A framework for continuous knowledge enrichment in enterprises where
humans and AI agents collaborate across systems of record.*

---

## Abstract

Enterprises accumulate knowledge across people, systems, and processes.
Traditionally, this knowledge is tacit — held in people's heads, buried in
Slack threads, implicit in SQL queries that "just work." The advent of AI
agents that can autonomously plan, execute, and learn creates both an
opportunity and a requirement: organizational knowledge must be externalized,
structured, and continuously maintained in a form that both humans and agents
can consume.

This paper presents a framework for managing organizational knowledge in an
agentic context. It introduces the organizational capability stack (purpose,
knowledge, skills, processes, operations), describes how knowledge
transforms across organizational levels, and proposes a signal processing
pipeline that continuously enriches the knowledge layer from operational
data and systems of record.

The paper further explores the convergence of knowledge and skills in
agentic systems, identifies three distinct knowledge flows (from actions,
from people, and from implicit observation), and examines how individual
knowledge becomes organizational through sharing and curation.

The framework is grounded in a concrete implementation — db-mcp, a semantic
layer for database querying — but the patterns generalize to any domain
where agents must act on institutional knowledge.

---

## 1. The Organizational Capability Stack

Organizations operate through five interdependent layers. These are not
orthogonal — they form a dependency graph with feedback loops.

```
Purpose / Strategy / Goals
         ↕
      Knowledge
         ↕
       Skills
         ↕
      Processes
         ↕
Operations / Operational Data
```

**Purpose** is the "why" — strategic direction, goals, intent. It
determines which knowledge matters, which skills to develop, which
processes to build. Without purpose, capability has no direction.

**Knowledge** is the "what we know" — domain expertise, institutional
memory, mental models, context. It exists independently of whether anyone
acts on it. Knowledge is the foundation upon which all other capability
is built.

**Skills** are knowledge made actionable — the "what we can do." Skills
require knowledge but add the dimension of practiced capability. You can
have knowledge without skill (understanding how engines work but unable
to rebuild one), but not skill without knowledge.

**Processes** are skills composed and sequenced — the "how we do things."
A process encodes which skills are applied, in what order, with what
handoffs and decision points. Processes depend on both knowledge (to
design them correctly) and skills (to execute them).

**Operations and operational data** are processes in motion — the "what's
actually happening." Operations are the runtime instantiation of processes,
and operational data is the exhaust they produce.

### The feedback loop

The dependency flows downward: purpose shapes knowledge, knowledge enables
skills, skills compose into processes, processes produce operations. But
operational data flows back upward to refine knowledge ("we learned that
step 3 is a bottleneck"), update skills ("this tool needs a new
capability"), and adjust strategy ("given what we're seeing, should we
change direction?").

This bidirectional flow is the organizational learning cycle — the OODA
loop or Deming cycle applied to institutional capability. The stack is
hierarchical going down, cyclical when learning is included.

---

## 2. Knowledge Across Organizational Levels

Knowledge is not uniform across an organization. It exists in qualitatively
different forms at each level, and it does not aggregate additively.

### Individual level

Personal expertise, mental models, tacit know-how. "I know how to debug
this system." "I know that the revenue table double-counts refunds."
This knowledge is high-fidelity but trapped — it walks out the door when
the person leaves.

### Team level

Shared context, common ground, collective mental models. "We all
understand how our service behaves under load." This is more than the
union of individual knowledge — it includes **transactive memory**: the
team knows who knows what. Coordination happens without explicit
communication because shared context reduces the need for it.

### Department / Function level

Codified practices, domain standards, tribal knowledge that persists
beyond individual tenure. "This is how we do data engineering here."
These are often partially written down (runbooks, style guides) but the
critical nuances remain oral tradition.

### Organization level

Institutional knowledge, strategic intelligence, cross-functional
synthesis. "We understand our market position and why we win." This
includes knowledge that no single person holds — it exists only in the
relationships between people and systems.

### The transformation, not aggregation

Nonaka and Takeuchi's SECI model describes knowledge transformation as a
spiral: tacit becomes explicit, individual becomes collective, collective
gets re-internalized as new tacit knowledge. Organizational knowledge is
not "bigger" individual knowledge — it is a qualitatively different thing.

Similarly, skills do not sum. Nelson and Winter's work on organizational
routines shows that collective capability is non-linear and
non-decomposable. Ten brilliant engineers who cannot work together produce
less than five mediocre engineers with strong interaction patterns. The
aggregation function is:

```
Org Capability = f(individual skills,
                   interaction patterns,
                   coordination mechanisms,
                   shared knowledge,
                   tools/infrastructure,
                   culture)
```

...where f is nonlinear and the interaction terms dominate.

### Topology mismatch

The capability stack maps differently onto organizational structure at
each layer:

| Layer | Natural topology | Org chart fit |
|---|---|---|
| Purpose | Tree (hierarchical) | High |
| Knowledge | Graph (networked) | Low |
| Skills | Clusters with overlaps | Medium |
| Processes | Chains (cross-cutting) | Low |
| Operations | Matrix | Medium |

Knowledge flows laterally (across teams) and bottom-up (frontline workers
know things executives don't). Organizations that force knowledge through
hierarchical channels lose signal. This is why knowledge management
initiatives that follow the org chart tend to fail — they impose the wrong
topology on a fundamentally networked phenomenon.

---

## 3. The Knowledge Externalization Imperative

### The traditional state

In most enterprises today, knowledge lives in four places:

1. **People's heads** — the most valuable, least accessible form
2. **Documents** — wikis, runbooks, READMEs that go stale within weeks
3. **Code** — configuration, business logic, SQL queries that encode
   assumptions implicitly
4. **Conversations** — Slack threads, email chains, meeting recordings
   that are searchable but not structured

This works when humans are the only consumers. A data analyst can read a
Slack thread, understand the context, and adjust their SQL accordingly.
The knowledge doesn't need to be structured because the human provides
the interpretation layer.

### The agentic shift

When AI agents enter the picture, tacit knowledge becomes a bottleneck.
Deloitte's 2025 research on enterprise AI architectures found that current
data architectures create friction for agent deployment because most
organizational data "isn't positioned to be consumed by agents that need
to understand business context and make decisions."

The problem is not agent capability — modern LLMs can reason, plan, and
execute. The problem is that the knowledge agents need to act correctly
has not been externalized into a machine-readable form.

Consider a query agent asked to calculate "monthly active users." Without
externalized knowledge, the agent must:

1. Guess which table contains user activity
2. Guess what "active" means (logged in? performed an action? excludes
   test accounts?)
3. Guess the time boundary logic (calendar month? rolling 30 days?
   fiscal month?)
4. Hope that the resulting SQL happens to match organizational intent

With externalized knowledge — a semantic layer containing table
descriptions, a business rule defining "active user," a metric definition
with time boundary semantics — the agent operates from institutional
knowledge rather than statistical inference.

### Knowledge as load-bearing infrastructure

In the agentic enterprise, the knowledge layer transitions from "nice to
have documentation" to load-bearing infrastructure. When agents make
autonomous decisions based on knowledge, the quality, currency, and
completeness of that knowledge directly determines the quality of
outcomes.

This reframes knowledge management from a documentation chore to an
engineering discipline. Knowledge needs:

- **Schema** — structured, typed, validated (not freeform wiki pages)
- **Versioning** — every change tracked, attributable, reversible
- **Testing** — knowledge can be validated against operational outcomes
- **Currency** — automated staleness detection and refresh cycles
- **Provenance** — every entry traceable to its source

---

## 4. Systems of Record as Signal Sources

Enterprises already generate a continuous stream of knowledge-relevant
events across their systems of record. These signals are currently
ignored by knowledge systems.

### The signal landscape

| System | Events generated | Knowledge signal |
|---|---|---|
| Version control (GitHub) | Commits, PRs, migrations | Schema changes, new tables, column renames |
| Issue tracking (Jira) | Tickets, labels, comments | Knowledge gaps, metric requests, data quality issues |
| Communication (Slack) | Messages, threads | Business rule candidates, term definitions, corrections |
| CRM (Salesforce) | Field additions, picklist changes | Dimension changes, enum updates |
| Data pipelines (dbt) | Model changes, test results | Schema drift, quality signals, freshness violations |
| ERP (NetSuite) | Account changes, org restructures | Fiscal dimensions, cost center updates |
| Observability (Datadog) | Alerts, incidents | Performance signals, connection health |
| Query execution | Results, errors, timeouts | Example candidates, gap detection, rule validation |

Each system produces thousands of events. The overwhelming majority carry
no knowledge-relevant signal. The challenge is extraction: identifying
the small fraction of events that imply a knowledge update.

---

## 5. The Signal-to-Knowledge Pipeline

We propose a five-stage pipeline that transforms raw events from systems
of record into validated knowledge updates.

```
Raw Event
   ↓  extraction (deterministic)
Signal
   ↓  interpretation (deterministic + agentic)
Intent
   ↓  disambiguation (deterministic + agentic)
Resolved Claim
   ↓  validation (deterministic)
Knowledge Layer Enriched
```

### Stage 1: Extraction — noise to signal

Extraction filters the event stream to identify knowledge-relevant
signals. This stage is purely deterministic — keyword matching, path
filters, regex patterns, structured field inspection.

The extractor does not need to understand the signal. It needs to
recognize that one exists. A commit touching `migrations/*.sql` is a
schema change candidate. A Slack message matching "X should always Y" or
"X means Y" is a rule candidate. A query returning zero rows after a
business rule was applied is a validation signal.

Output: a structured `Signal` record with source metadata, raw content,
category classification, and a connection hint (which organizational
knowledge domain this signal likely affects).

**Design principle:** extraction is cheap, interpretation is expensive.
Filter aggressively before engaging reasoning.

### Stage 2: Interpretation — signal to intent

Interpretation determines what the signal means in context. This is where
the existing knowledge layer becomes essential — you cannot interpret a
signal without knowing what you already know.

A schema change signal ("ADD COLUMN orders.discount_type") requires the
current schema to determine whether this is a new dimension, a denormalized
field, or a migration artifact. A Slack message about "active users"
requires the existing business rules and metric definitions to determine
whether this is a new rule, a refinement of an existing rule, or a
contradiction.

**Deterministic interpretation** handles structurally unambiguous signals:
SQL DDL parsing, dbt test result classification, connection health checks.

**Agentic interpretation** handles ambiguous signals: natural language
messages, vague ticket descriptions, implicit assumptions in code changes.
The LLM reads the signal plus the current knowledge state and produces a
structured interpretation — what knowledge update this signal implies,
which entities it affects, and a draft of the update content.

The critical insight: **interpretation quality is bounded by knowledge
quality.** An empty knowledge vault provides no context for interpretation.
A rich vault enables precise interpretation. This creates a virtuous cycle:
better knowledge enables better signal interpretation, which produces
better knowledge.

### Stage 3: Disambiguation — intent to resolved claim

The interpretation may be ambiguous along several dimensions:

- **Entity ambiguity:** "Revenue" maps to multiple metrics. "The users
  table" exists in multiple connections.
- **Scope ambiguity:** Does this rule apply to one connection, a group,
  or the entire organization?
- **Semantic ambiguity:** Is this a new rule or a refinement of an
  existing one?
- **Conflict:** The signal implies something that contradicts existing
  knowledge.

Disambiguation resolves each ambiguity to a specific claim: "add this
business rule to this connection's knowledge vault" or "update this
metric definition" or "flag conflict between new signal and existing
rule #23."

**Resolution strategies:**

| Ambiguity type | Strategy |
|---|---|
| Entity → multiple matches | Semantic similarity ranking, usage frequency, connection scoping |
| Scope → unclear breadth | Default to narrowest scope (single connection), surface for broadening |
| Semantic → new vs. update | Exact match → update; partial match → surface both for human decision |
| Conflict detected | Always surface for human decision; never silently override |

**Design principle:** when in doubt, narrow the scope and surface for
confirmation. False negatives (missed updates) are recoverable; false
positives (wrong updates) corrupt the knowledge base.

### Stage 4: Validation — resolved claim to accepted update

Before writing to the knowledge layer, the claim passes through
deterministic validation gates:

1. **Structural validity.** Does the update conform to the knowledge
   layer's schema? Is the YAML/JSON well-formed? Do referenced entities
   (tables, columns, metrics) actually exist?

2. **Consistency check.** Does this update contradict other knowledge?
   If adding a rule "exclude test accounts," does any approved example
   include test accounts?

3. **Disposition gate.** Rather than synthetic confidence scores (which
   obscure their reasoning), the pipeline evaluates observable criteria
   to determine disposition:

   | Disposition | Criteria |
   |---|---|
   | **Auto-apply** | Source is structured (schema catalog, dbt docs) AND entity match is exact AND no conflicts AND change is additive |
   | **Surface for review** | Source is unstructured (Slack, commit message) OR entity match is fuzzy OR potential conflict OR change modifies existing knowledge |
   | **Discard** | No entity match found OR source context insufficient to interpret |

   Each signal carries its **evidence** — the observable factors that
   determined its disposition — rather than a numeric score. The curator
   sees: "Source: senior data engineer in #data-eng. Entity match: exact
   (users.is_test column exists). Corroborated by 3 queries that already
   filter on is_test. No conflicts." This is actionable. A number
   between 0 and 1 is not.

4. **Write gate.** A schema registry validates the typed update before
   any write reaches the knowledge store. This is the final structural
   check — the knowledge layer's equivalent of a database constraint.

**Design principle:** no LLM in the validation gate. Interpretation
happened upstream. Validation is mechanical: does this update meet the
structural and consistency requirements for a knowledge write?

### Stage 5: Enrichment — accepted update to knowledge layer

The validated update is applied to the knowledge store. Every write is:

- **Typed** — descriptions, rules, metrics, examples, gaps have distinct
  schemas and write paths
- **Provenance-tracked** — which signal, from which source, at what
  confidence, interpreted by which mechanism
- **Reversible** — git history for version-controlled vaults, append-only
  with soft deletes for operational stores
- **Attributed** — `added_by: signal_pipeline, source: github:PR#1234,
  confidence: 0.87, confirmed_by: user:jane`

**Deposition is safer than erosion.** The pipeline should prefer creating
new entries over updating existing ones, and should flag conflicts rather
than resolving them silently. Adding knowledge is low-risk; modifying or
removing knowledge can cascade into incorrect agent behavior.

---

## 6. Knowledge Architecture for the Agentic Enterprise

### Hierarchical knowledge with inheritance

Enterprise knowledge naturally organizes hierarchically:

```
Organization-wide defaults
├── Team/Domain group defaults
│   ├── Connection-specific knowledge
│   └── Connection-specific knowledge
└── Team/Domain group defaults
    └── Connection-specific knowledge
```

Business rules like "never expose PII" apply organization-wide. Rules
like "fiscal year starts April 1" apply to a finance domain group.
Table descriptions are connection-specific but may inherit shared
dimensions from their group.

**Inheritance chain:** connection overrides group, group overrides
organization. Most specific wins. Rules and descriptions merge
(additive); credentials and operational state never inherit.

### Knowledge types

| Type | What it encodes | Volatility | Inheritance |
|---|---|---|---|
| Schema descriptions | What tables/columns mean | Medium — changes with schema | Group + connection |
| Business rules | Constraints and filters for correct queries | Low — changes with policy | Org + group + connection |
| Metric definitions | How KPIs are calculated | Low — changes with strategy | Org + group |
| Query examples | Approved query patterns | Medium — changes with schema and rules | Connection |
| Domain model | Entity relationships and concepts | Low | Group + connection |
| Knowledge gaps | Unmapped business terms | High — created and resolved frequently | Connection |
| Operational signals | Quality, freshness, health | High — continuous stream | Connection |

### The knowledge graph topology

While the configuration hierarchy is tree-structured (org → group →
connection), the knowledge itself forms a graph:

- A **metric** references **columns** across multiple **tables**
- A **business rule** constrains queries on specific **tables** in
  specific **connections**
- A **dimension** is shared across **connections** within a **group**
- A **gap** in one connection may be resolved by a **rule** from another

This graph topology — knowledge as a network, not a hierarchy — is what
enables cross-domain reasoning. An agent querying one database can
leverage knowledge from another because the semantic relationships are
explicit and traversable.

---

## 7. The Agentic Transformation

### What changes

In a traditional enterprise, the capability stack operates through human
mediation at every layer. Knowledge lives in heads. Skills are embodied
in individuals. Processes depend on human coordination. Operations require
human execution.

In the agentic enterprise:

| Layer | Traditional | Agentic |
|---|---|---|
| Purpose | Human strategy | Human strategy (unchanged) |
| Knowledge | Tacit, human-held | Externalized, machine-readable, continuously maintained |
| Skills | Human competencies | Agent capabilities + human competencies, composable |
| Processes | SOPs, manual workflows | Multi-agent orchestration, protocol-mediated (MCP, ACP) |
| Operations | Human execution with tools | Autonomous execution with guardrails, traces, feedback |

### The composability shift

Human skills aggregate non-linearly — the interaction terms dominate.
Agent capabilities are fundamentally more composable. An agent's skills
are declarative, discoverable, and don't carry coordination overhead.
The aggregation function becomes closer to additive, though orchestration
quality still matters.

This means organizational capability in an agentic context is more
modular: you can add a new agent capability (a tool, a skill, a prompt
template) and it immediately composes with everything else. The
traditional problem of "ten brilliant engineers who can't work together"
doesn't apply to agents — their interaction patterns are protocols, not
politics.

### The knowledge layer becomes central

In the traditional enterprise, the knowledge layer is a documentation
concern — useful but not load-bearing. In the agentic enterprise, it
becomes the critical infrastructure:

- Agents **read** the knowledge layer before every action (pre-execution
  knowledge consultation)
- Agents **write** to the knowledge layer after every action (post-execution
  signal emission)
- The quality of agent output is **directly proportional** to the quality
  of the knowledge layer
- Knowledge **currency** (how up-to-date it is) determines whether agents
  make decisions based on reality or on stale assumptions

This is the fundamental shift: knowledge management transitions from a
periodic human activity ("let's update the wiki") to a continuous
automated process ("every execution enriches the knowledge base").

### Dissolving topology mismatches

The agentic enterprise has the potential to dissolve the topology
mismatches between how capability actually works and how org charts
pretend it works:

- **Knowledge** can be externalized into semantic layers and knowledge
  graphs that are traversable by any actor, regardless of org chart
  position
- **Skills** become composable across human and agent actors through
  standard protocols
- **Processes** can be implemented as multi-agent orchestration without
  the political friction of crossing departmental boundaries

The org chart becomes a governance and accountability structure (who is
responsible) rather than a capability structure (who can do what), because
capability is externalized and composable.

---

## 8. The Knowledge-Skills Convergence

### When knowledge becomes skills

In the traditional capability stack, knowledge and skills are distinct
layers — knowledge is "what we know," skills are "what we can do." But
when the consumer of knowledge is an agent, this distinction collapses.

Consider a business rule: "Active users exclude test accounts — filter
WHERE is_test = false." To a human, this is knowledge — a fact to
remember. To an agent, this is a skill — a procedural instruction to
follow when generating queries. The rule does not change; the consumer's
relationship to it does.

This convergence is not just semantic. Modern agent frameworks (Claude
Code's skills system, Cursor's rules, Codex's AGENTS.md) already treat
knowledge as executable instructions. A "skill" in Claude Code is a
markdown file with context about when and how to apply it — which is
exactly what a business rule, a coding pattern, or an architectural
decision is.

### The taxonomy

Not all knowledge converges with skills. The distinction is between
knowledge consumed by agents as instructions versus knowledge consumed
by systems as structured data:

| Type | Format | Consumer | Example |
|---|---|---|---|
| **Skills** (rules, patterns, decisions) | Prose (markdown) | Agent interprets and follows | "Fiscal year starts April 1" |
| **Structured knowledge** (metrics, schema, bindings) | YAML/JSON | System parses and compiles | `DAU = COUNT(DISTINCT user_id) WHERE...` |
| **Examples** (query patterns) | SQL + intent pairs | System uses for few-shot matching | "monthly revenue → SELECT SUM..." |

Skills are instructions for agents. Structured knowledge is input to
compilers. Both are knowledge; they serve different consumers.

A metric definition like "DAU = COUNT(DISTINCT user_id) WHERE
last_active >= CURRENT_DATE - 1 AND is_test = false" has a SQL
expression, dimensions, parameters, and bindings. An agent does not
interpret it as prose — a query engine compiles it deterministically.
This is not a skill; it is structured data.

A rule like "run bun build before PyInstaller" or "TUI prompts are
externalized as markdown files in the prompts/ directory" is a
procedural instruction that an agent follows when a context matches.
This IS a skill.

The knowledge layer is therefore **two stores**: skills for agent
behavior, structured data for system compilation. Connected by
provenance (both trace back to signals), but different formats for
different consumers.

### Hierarchical skills

Agent skill systems already support hierarchy that maps to organizational
knowledge scoping:

| Organizational scope | Skill location |
|---|---|
| Organization-wide | Managed settings / shared repo |
| Team or domain | Project-level skill directory |
| Connection or package-specific | Nested skill directory, path-scoped |

Skills can be scoped to activate only when working with matching files
or directories, providing automatic context filtering without manual
selection. A database-specific rule activates only when the agent works
with that database's files.

This means the hierarchical configuration discussed for enterprise
knowledge (org → group → connection) maps directly to the agent's
native skill discovery mechanism. No custom inheritance system is
needed — the agent platform provides it.

### Implications for onboarding

The traditional approach to teaching an agent about a domain is explicit
onboarding: run a setup wizard, describe tables, add rules, provide
examples. This is a one-time manual effort that produces a knowledge
base.

With the knowledge-skills convergence, onboarding becomes continuous
learning. The system watches the user work — queries executed,
corrections made, patterns followed — and proposes skills that codify
what it observes. The user reviews and approves. Over time, the skill
library grows from observed behavior, not explicit teaching.

The onboarding wizard does not disappear — it is valuable for cold
start. But it transitions from the primary knowledge acquisition method
to a bootstrapping step, after which continuous learning dominates.

---

## 9. Three Knowledge Flows

Knowledge enters an organization through three distinct flows, each
requiring different capture mechanisms.

### Flow 1: Knowledge from actions

The most tractable flow. Knowledge is embedded in artifacts that people
produce: code commits, configuration changes, query patterns, document
edits. These are observable, timestamped, and attributable.

| Signal source | What it carries | Capture mechanism |
|---|---|---|
| Git commits | Schema changes, architecture decisions, bug fixes | Filesystem watch, git log analysis |
| Query execution | Successful patterns, failure modes, corrections | Execution traces |
| Configuration changes | Operational constraints, deployment rules | File monitoring |
| Document edits | Term definitions, process descriptions | File monitoring |

This flow is what most knowledge extraction systems target, including
the signal-to-knowledge pipeline described in Section 5. The signals
are explicit artifacts — the challenge is interpretation, not capture.

### Flow 2: Knowledge from people

Knowledge transmitted through human communication — conversations,
reviews, discussions. Higher value per signal but harder to capture
without surveillance.

| Signal source | What it carries | Capture mechanism |
|---|---|---|
| Code review comments | Design rationale, pattern corrections | API (GitHub, GitLab) |
| Chat messages | Term definitions, business rules, corrections | API (Slack, Teams) — scoped channels |
| Meeting transcripts | Decisions, action items, context | Transcription service → ingest |
| Pair programming | Tacit expertise, debugging approaches | No good capture today |

The critical challenges:

**Attribution and consent.** Knowledge from a person should reference
them as the source. Capturing what someone said and turning it into
organizational knowledge raises questions about ownership and permission.

**Signal-to-noise ratio.** Communication channels produce vastly more
noise than artifact-based signals. A Slack channel may have thousands
of messages per week; three carry knowledge-relevant signal. Extraction
must be highly selective.

**Context dependency.** A statement like "that column is unreliable"
only makes sense in context — which column, which table, why unreliable.
The interpretation stage must reconstruct context that the original
speakers shared implicitly.

### Flow 3: Knowledge from implicit observation

The hardest flow. Knowledge exists in behavior that produces no explicit
artifact — debugging sessions, research browsing, trial-and-error
iterations, pattern recognition from experience.

| Signal | What it implies | Observable through |
|---|---|---|
| Repeated edits to same file | Something is hard to get right | File modification frequency |
| Commit followed by revert | An approach was tried and failed | Git history |
| Query correction (0 rows → modified WHERE → results) | A filter assumption was wrong | Execution traces |
| Long research session before a change | The change required learning | Time-between-commits analysis |
| Same fix applied across multiple files | A cross-cutting pattern or rule | Diff similarity analysis |

This knowledge is the most valuable and least capturable. The gap
between "what happened" (observable) and "why it happened" (tacit)
can only be bridged by inference — either by the agent interpreting
behavioral patterns, or by the human explicitly narrating their
reasoning.

The practical approach: capture the behavioral signals (reverts,
repeated edits, execution corrections) and use agentic interpretation
to propose knowledge. The human confirms or corrects the inference.
Over time, the system learns which behavioral patterns reliably indicate
which knowledge types.

### From individual to organizational knowledge

Individual knowledge becomes organizational through a fourth flow:
**sharing and curation.**

```
Individual                              Organizational
─────────────                           ──────────────
Your work → signals → your skills       
                          │             
                    propose to team →   team curator reviews
                                              │
                                              ▼
                                        shared skill library
                                              │
                                              ▼
                                        all team agents read
```

The sharing mechanism requires:

- **A promotion step** — the individual (or their agent) nominates a
  local skill for team-wide use
- **A curation step** — a team curator reviews the proposed skill for
  accuracy, scope, and relevance
- **A distribution mechanism** — approved team skills are available to
  all team members' agents
- **Provenance preservation** — the shared skill traces back to the
  individual who proposed it, the signal it came from, and the curator
  who approved it

This mirrors how organizational knowledge actually forms: someone
discovers something, shares it, a domain expert validates it, and it
becomes institutional knowledge. The automation replaces the informal
and unreliable parts (sharing via Slack, validation via tribal memory)
with a structured workflow.

---

## 10. Related Work: The LLM Wiki Pattern

Karpathy (2025) describes a pattern for building personal knowledge
bases using LLMs that shares significant conceptual overlap with the
framework presented here. The "LLM Wiki" proposes three layers:

- **Raw sources** — immutable documents (articles, papers, notes)
- **The wiki** — LLM-generated and maintained markdown files,
  interlinked, with summaries, entity pages, and cross-references
- **The schema** — conventions and workflows that govern how the
  LLM maintains the wiki

The wiki serves as a "persistent, compounding artifact" — knowledge
compiled once and kept current, not re-derived on every query. The
LLM handles all maintenance: summarizing, cross-referencing, filing,
consistency checking. The human curates sources, directs analysis, and
asks questions. Key operations include **ingest** (add a source, LLM
integrates it across the wiki), **query** (ask questions, good answers
filed back into the wiki), and **lint** (health-check for
contradictions, stale claims, orphan pages).

### Convergence

The core insight is identical in both frameworks: **LLMs do the
maintenance, humans do the curation.** Knowledge compounds because
the cost of bookkeeping drops to near zero. Both architectures use
immutable sources, an LLM-maintained knowledge layer, and a feedback
loop where queries improve the knowledge base. Both converge on
markdown files in a git repo as the storage substrate.

### Divergence

The LLM Wiki is **pull-based**: the human explicitly drops sources
in and supervises ingestion. The signal-to-knowledge pipeline is
**push-based**: signals are automatically extracted from work activity,
and the human reviews proposals rather than directing ingestion.

The LLM Wiki's output is **freeform prose** — wiki pages with
cross-references, suitable for human reading and LLM-assisted Q&A.
The pipeline's output is **typed knowledge** — skills (agent
instructions) and structured data (metric definitions, schema types)
— optimized for autonomous agent consumption.

The LLM Wiki assumes a **single human + LLM** collaboration. The
pipeline addresses **organizational** knowledge with multiple
contributors, curation workflows, access control, and sharing between
individual and team knowledge stores.

### Synthesis

The two approaches are complementary. The LLM Wiki handles the
**manual ingest** case well — a human finds an article, drops it in,
the LLM integrates it. The signal-to-knowledge pipeline handles the
**automatic extraction** case — signals from work activity are
continuously processed without human initiation. A complete knowledge
system supports both: manual ingest for documents and articles that
the user encounters, automatic extraction for the continuous stream
of signals from daily work. The **lint** operation maps directly to
scheduled knowledge health-checks (staleness detection, contradiction
flagging, gap identification) already described in the pipeline
architecture.

---

## 11. Implementation Patterns

### Pattern 0: Knowledge as agent skills

For knowledge that agents consume as instructions (rules, patterns,
decisions), use the agent's native skill format rather than a custom
knowledge store. In Claude Code, this means `.claude/skills/SKILL.md`
files with YAML frontmatter for scoping and activation. In other agent
frameworks, the equivalent convention. This eliminates the "how do
agents read the knowledge" problem — they already know how to read
their own skill format. The signal-to-knowledge pipeline's output for
these knowledge types is a draft skill file, not a custom YAML entry.

### Pattern 1: Knowledge vault with semantic layer

A structured file-based knowledge store, version-controlled, with typed
schemas for each knowledge type. The vault is the authoritative source
for agent behavior — agents consult it before every action and write back
to it after.

```
vault/
├── schema/descriptions.yaml      # what tables and columns mean
├── instructions/business_rules.yaml  # query constraints
├── metrics/catalog.yaml          # KPI definitions and bindings
├── training/examples/            # approved query patterns
├── domain/model.yaml             # entity relationships
└── state/signals.jsonl           # operational signal stream
```

### Pattern 2: Signal ingestion API

A single endpoint that accepts normalized signals from any source.
Adapters transform system-specific events into the common signal format.
The processing pipeline handles interpretation, disambiguation,
validation, and enrichment.

```
POST /api/signals/ingest
{
  "source": "github",
  "source_ref": "PR #1234",
  "kind": "schema_change",
  "connection": "prod-postgres",
  "content": "...",
  "confidence": 0.9
}
```

### Pattern 3: Tiered processing

Deterministic processing for unambiguous signals (schema parsing, health
checks, freshness monitoring). Agentic processing for ambiguous signals
(natural language interpretation, conflict resolution, rule drafting).
The LLM is a tool in the pipeline, not the pipeline itself.

### Pattern 4: Confidence-gated writes

Every knowledge update carries a confidence score. High-confidence updates
auto-apply. Medium-confidence updates surface for human confirmation.
Low-confidence updates are logged for batch review. The threshold is
tunable per organization based on risk tolerance.

### Pattern 5: Provenance-first

Every knowledge entry records its origin: which signal, from which system,
interpreted by which mechanism, confirmed by whom. This enables debugging
("why did the agent use this rule?"), auditing ("who approved this
metric definition?"), and trust ("this rule was confirmed by three
independent signals from production execution").

---

## 12. Open Questions

**1. Cold start.** A new knowledge vault is empty, and the signal pipeline
depends on existing knowledge for interpretation context. The cold start
is not a special problem — it is the signal pipeline running in **bulk
extraction mode** against existing sources. Schema metadata from database
catalogs, descriptions from dbt projects, metric definitions from BI
tools, and patterns from query logs can be extracted in batch. High-
confidence structural knowledge (column types, foreign keys, dbt
descriptions) auto-populates without review. The curator focuses on the
ambiguous fraction — business rules, term definitions, organizational
conventions. For a typical enterprise with a dbt project and 10
databases, the first hour of bulk extraction produces a useful vault;
the first week of curation makes it comprehensive. Manual onboarding
remains valuable as a complement but transitions from the primary
knowledge acquisition method to a bootstrapping accelerant.

**2. Knowledge decay.** How do you detect and handle stale knowledge?
A business rule that was correct six months ago may no longer apply.
Staleness detection (monitoring validation frequency, flagging unexercised
rules) is necessary but may not be sufficient for rules that are actively
used but subtly wrong.

**3. Multi-tenancy and access control.** In an enterprise, not all
knowledge should be visible to all agents. A finance agent should see
fiscal rules; a marketing agent should not see compensation data. The
knowledge layer needs access control that maps to organizational
boundaries — but the strength of cross-domain knowledge is precisely
that it crosses those boundaries.

**4. Conflicting knowledge.** Different teams may define the same business
term differently. "Active user" in the product team means "logged in
within 30 days." In the finance team, it means "has an active
subscription." Both are correct in their context. The knowledge layer
must support contextual definitions without forcing premature
reconciliation.

**5. Trust calibration.** When should an agent trust the knowledge layer
versus its own reasoning? If the knowledge says "fiscal year starts
January 1" but the data clearly shows April boundaries, should the agent
follow the rule or flag the discrepancy? The answer is "flag the
discrepancy" — but implementing this requires agents that can reason
about knowledge quality, not just consume it.

**6. Measurement.** How do you measure the quality of a knowledge layer?
Possible metrics include: signal-to-noise ratio (fraction of signals that
produce accepted updates), knowledge coverage (fraction of business terms
with definitions), staleness index (average age of last validation per
knowledge entry), agent accuracy improvement (query correctness over time
as knowledge accumulates). None of these are standardized.

---

## 13. Conclusion

The agentic enterprise does not just automate existing processes — it
changes the aggregation function for organizational capability.
Knowledge transitions from tacit and human-held to explicit,
machine-readable, and continuously maintained. In the agentic context,
much of this knowledge converges with skills — procedural instructions
that agents follow — collapsing two layers of the capability stack into
one. The remaining knowledge (metrics, schema, structured data) serves
as input to deterministic compilation rather than agent interpretation.

Knowledge enters the system through three flows: from explicit actions
(commits, queries, documents), from people (conversations, reviews,
discussions), and from implicit observation (behavioral patterns,
trial-and-error, debugging sessions). Each flow requires different
capture mechanisms but feeds the same pipeline. Individual knowledge
becomes organizational through a sharing and curation workflow that
mirrors how institutions have always formed knowledge — someone
discovers something, shares it, an expert validates it, and it becomes
institutional.

The signal-to-knowledge pipeline — extraction, interpretation,
disambiguation, validation, enrichment — provides the mechanism for
continuous knowledge maintenance. The LLM handles the bookkeeping that
humans abandon: updating cross-references, flagging contradictions,
maintaining consistency across hundreds of knowledge entries. The human's
role shifts from maintenance to curation — directing what matters, not
filing what's known.

This transforms the knowledge layer from a static artifact that decays
over time into a living system that improves with every operational
cycle. The tedious part of maintaining a knowledge base is not the
reading or the thinking — it is the bookkeeping. When the cost of
bookkeeping drops to near zero, knowledge compounds.

The trillion-dollar question is not whether agents can reason — they can.
It is whether organizations can externalize their knowledge fast enough
to make that reasoning useful.

---

## References

- Karpathy, A. (2025). LLM Wiki: A pattern for building personal
  knowledge bases using LLMs. GitHub Gist.
- Nonaka, I., & Takeuchi, H. (1995). *The Knowledge-Creating Company.*
  Oxford University Press.
- Nelson, R. R., & Winter, S. G. (1982). *An Evolutionary Theory of
  Economic Change.* Harvard University Press.
- Teece, D. J. (2007). Explicating Dynamic Capabilities. *Strategic
  Management Journal*, 28(13), 1319-1350.
- Zollo, M., & Winter, S. G. (2002). Deliberate Learning and the
  Evolution of Dynamic Capabilities. *Organization Science*, 13(3),
  339-351.
- Nguyen, T., & Zeng, Y. (2017). A Theoretical Model of Organizational
  Capability. *Proceedings of the International Conference on Engineering
  Design.*
- TOGAF Standard, Version 9.2. The Open Group Architecture Framework.
- Deloitte Insights (2025). Enterprise AI Architecture: Positioning Data
  for Agentic Systems.
- California Management Review (2025). The Agentic Operating Model:
  Organizational Design for Autonomous AI.
- MIT Sloan Management Review / BCG (2025). AI Agents as Organizational
  Actors.
