# DataMCP P0 Product Contract

**Status**: Draft  
**Date**: 2026-03-05  
**Positioning**: AI-native enterprise data control-plane (not a standalone BI tool, not just text-to-SQL).

Related note: `docs/datamcp-fsm-runtime-note.md`.

## 1. Problem Statement

Enterprises are moving to AI-driven operations, but data answers remain inconsistent across systems. The core failure mode is not query syntax; it is semantic drift:

- "same metric, different meaning" across teams/sources
- weak reproducibility of AI-generated answers
- poor auditability for high-stakes decisions

DataMCP P0 exists to make AI answers over enterprise data **trustable, governable, and repeatable**.

## 2. Product Scope (P0)

DataMCP P0 will:

1. Resolve intent against an org/domain semantic core.
2. Compile a semantic meta-query (internal AST).
3. Resolve to connection-bound execution plans.
4. Execute and aggregate across one or more sources.
5. Return answer + records + provenance + confidence + policy trace.
6. Accumulate knowledge from serving events into a governed lifecycle queue.

DataMCP P0 will not:

1. Be a universal connector framework for every data system.
2. Replace warehouse modeling or dbt.
3. Guarantee autonomous root-cause analysis.
4. Depend on Substrait for core operation (optional later).

## 3. Core Architecture Contract

Semantics and execution are separate layers:

1. **Semantic Core (org/domain scoped)**
2. **Connection Bindings (physical mappings per source)**
3. **Resolver/Planner (semantic -> physical)**
4. **Connection Executors (SQL/API/file)**
5. **Aggregator (deterministic merge/post-agg)**
6. **Synthesis (thin NL layer over deterministic output)**
7. **Knowledge Loop (observation -> candidate -> review -> promotion)**

Hard rule: semantics are never owned by a single connection.
Hard rule: promoted knowledge must be human-approved in P0/V1.
Hard rule: cardinality (`ONE` vs `MANY`) is first-class intent, not a post-hoc guess.

## 4. Input Contract

`answer_intent` request contract (P0):

```json
{
  "intent": "string",
  "org": "string",
  "domain": "string",
  "connections": ["optional", "subset", "of", "allowed", "connections"],
  "time_context": {
    "start": "optional ISO-8601",
    "end": "optional ISO-8601",
    "timezone": "optional IANA tz"
  },
  "constraints": {
    "max_cost": "optional numeric budget",
    "max_latency_ms": "optional integer",
    "allow_partial": true
  },
  "options": {
    "explain": true,
    "return_records": true
  }
}
```

## 5. Output Contract

`answer_intent` response contract (P0):

```json
{
  "status": "success|partial|error",
  "answer": "natural-language summary",
  "records": [{"...": "canonical record fields"}],
  "meta_query": {"...": "semantic AST"},
  "resolved_plan": {"...": "physical plan + routing"},
  "result_shape": {
    "expected_cardinality": "ONE|MANY",
    "observed_cardinality": "ONE|MANY|EMPTY",
    "cardinality_validated": true
  },
  "provenance": {
    "sources": ["connection/source identifiers"],
    "executions": ["execution_id values"],
    "transform_chain": ["ordered ops"]
  },
  "confidence": {
    "semantic_confidence": 0.0,
    "binding_confidence": 0.0,
    "execution_confidence": 0.0,
    "aggregation_confidence": 0.0,
    "knowledge_coverage_confidence": 0.0,
    "answer_confidence": 0.0
  },
  "policy": {
    "checks": ["policy checks applied"],
    "decisions": ["confirm/deny/allow details"],
    "cardinality_checks": ["planner/executor cardinality checks applied"]
  },
  "warnings": ["coverage gaps, partial failures, assumptions"]
}
```

## 6. Guarantees (P0)

1. **Reproducibility**: same semantic core + bindings + request constraints -> same resolved plan.
2. **Traceability**: every answer maps to explicit sources, execution IDs, and transform steps.
3. **Policy enforcement**: execution respects existing guardrails (read/write, cost, confirmation).
4. **Deterministic core**: planner/resolver/aggregator are testable without LLM dependence.
5. **Backward compatibility**: existing tools (`run_sql`, `validate_sql`, `get_result`, `api_execute_sql`) remain functional.
6. **No silent knowledge mutation**: no auto-promotion of candidates in P0/V1.
7. **Cardinality enforcement**: `ONE` intents that return multiple rows are surfaced as violations, not silently accepted.

## 7. Non-Guarantees (P0)

1. No guarantee of fully correct business interpretation when semantic artifacts are incomplete.
2. No guarantee that partial answers always preserve all requested dimensions.
3. No SLA for arbitrary high-cardinality cross-source joins in P0.
4. No guarantee of perfect static cardinality inference when schema metadata is incomplete/stale.

## 8. Knowledge Lifecycle Contract (P0)

Lifecycle states:

1. `Observed`
2. `Candidate`
3. `Conflicted`
4. `Approved`
5. `Deprecated`

Trigger model (candidate creation):

1. Failed binding -> candidate binding proposal.
2. Low-confidence resolution -> candidate rule/template clarification.
3. User correction -> high-priority candidate.
4. Clarification-required ambiguity -> disambiguation rule candidate.
5. Successful novel pattern -> reusable template candidate.

Conflict policy:

1. Contradictory candidates for the same semantic object move to `Conflicted`.
2. `Conflicted` items are blocked from promotion until explicit human resolution.
3. Resolver ignores `Conflicted` entries for production planning.

## 9. Query and Data Rules (P0)

### Query Cardinality Contract

Cardinality vocabulary:

1. `ONE`: expected single logical record (or scalar).
2. `MANY`: expected collection/stream of records.

Validation model (in order):

1. Semantic declaration: template/node marks `expected_cardinality`.
2. Static analysis: AST checks (`LIMIT 1`, aggregate-no-group, etc.).
3. Schema/API metadata: PK/UNIQUE constraints or endpoint/entity contract.
4. Runtime enforcement: compare expected vs observed row shape.

Violation policy:

1. `ONE` + observed `MANY` -> `cardinality_violation` warning/error with downgraded confidence.
2. `MANY` + observed `ONE` is valid (collection may contain one row).
3. `ONE` + observed `EMPTY` is valid but explicit (`not_found` style semantics).

Aggregator cardinality policy:

1. `1:1` joins: allowed.
2. `1:N` joins: allowed only with explicit aggregation rule.
3. `N:M` joins: blocked unless bridge mapping is declared in bindings.

Conflict resolution precedence:

1. Explicit binding override
2. Semantic rule/template
3. Source priority policy
4. Freshness tie-breaker

## 10. MCP Knowledge Tools (P0 Surface)

1. `knowledge_status` (coverage, staleness, queue stats)
2. `knowledge_queue_list` (pending candidates/conflicts)
3. `knowledge_candidate_promote`
4. `knowledge_candidate_reject`
5. `knowledge_diff` (impact preview before approval)
6. `knowledge_explain` (evidence chain for approved metric/rule/binding)
7. `cardinality_explain` (why planner/executor decided `ONE` or `MANY`)

## 11. Launch Metrics and Gates

P0 ships only if all gates pass on target pilot intents:

1. **Correctness**: materially higher judged correctness vs current flow.
2. **Repeatability**: same intent yields stable plan/output under fixed inputs.
3. **Auditability**: 100% of answers include provenance + confidence vector.
4. **Safety**: policy violations are blocked or require explicit confirmation.
5. **Adoption**: pilot users choose `answer_intent` over direct SQL path for target scenarios.
6. **Learning quality**: accepted candidates improve coverage without regression spikes.
7. **Cardinality quality**: low false-positive rate on `cardinality_violation` for pilot intents.

## 12. Kill Criteria

Stop or narrow scope if, after pilot:

1. no measurable correctness/repeatability lift,
2. provenance/confidence is not trusted by operators,
3. latency/cost overhead outweighs business value for target workflows.
