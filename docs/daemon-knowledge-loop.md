# Daemon Knowledge Loop

## Goal

Keep the executor-style daemon MCP surface minimal while still using and improving the
connection knowledge layer.

Daemon mode should stay:

- `prepare_task(question, connection?, context?)`
- `execute_task(task_id, sql, confirmed=False)`

No extra learning tools should be required for the agent.

## Current State

The daemon path already reads from the connection knowledge layer during
`prepare_task(...)`.

Current inputs assembled into the task context:

- schema descriptions
- candidate tables and columns
- inferred join hints
- relevant examples, including saved SQL
- relevant rules
- focused domain-model excerpts
- focused SQL-rules excerpts
- optional heuristic `suggested_sql`

That means query reuse is already present:

- previously saved examples are surfaced back to the agent
- the agent can adapt those examples instead of rediscovering SQL from scratch

## Gap

Daemon mode currently consumes the knowledge layer, but it does not contribute back to it.

What is missing:

- automatic capture of successful daemon queries as candidate examples
- automatic capture of daemon failures as candidate learnings
- recording which context artifacts were actually useful

This is a product gap, not a tooling gap.

## Design Constraint

Do not add new daemon MCP tools for learning.

Reasons:

- keeps the executor-like MCP surface small
- avoids pushing more protocol burden onto the agent
- keeps learning as backend/control-plane responsibility

The external agent should stay responsible for reasoning.
The backend should stay responsible for retrieval, execution, and learning capture.

## Proposed Backend-Owned Learning

### 1. Successful Query Capture

After a successful `execute_task(...)` for a read query, persist a draft example candidate with:

- question
- connection
- SQL
- result shape metadata
- referenced tables if available
- source task id

This should write to a draft/candidate area first, not directly into the curated example set.

### 2. Failure Capture

When validation or execution fails, persist a learning candidate with:

- question
- SQL
- error message
- connector/dialect
- relevant context artifacts used during `prepare_task(...)`

This gives us backend-owned failure learnings without asking the agent to save them explicitly.

### 3. Context Usage Signals

Record which knowledge artifacts were included and which ones appear to have mattered:

- example ids surfaced
- rules surfaced
- tables surfaced
- whether execution succeeded on first try

This is useful for ranking and future retrieval quality.

## What Should Not Be Automatic

These should remain curated or promoted later:

- direct edits to business rules
- direct edits to domain model
- unconditional promotion of every successful query into examples

The backend should collect candidates, not silently rewrite curated knowledge.

## Recommended Rollout

### Phase 1

Add backend draft capture only:

- successful query candidates
- failure candidates
- context usage metadata

No MCP surface changes.

### Phase 2

Add promotion/review workflow through existing db-mcp surfaces:

- UI
- insights
- existing knowledge management flows

### Phase 3

Use captured signals to improve retrieval ranking inside `prepare_task(...)`.

## Bottom Line

The daemon path already reuses the knowledge layer.

The next step is to make it contribute back on the backend:

- without adding new daemon tools
- without adding an internal model
- without making the agent manage learning protocol explicitly
