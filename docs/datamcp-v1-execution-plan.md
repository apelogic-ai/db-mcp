# DataMCP V1 Execution Plan (db-mcp)

**Status**: Proposed implementation plan  
**Date**: 2026-03-05  
**Scope**: Evolve `db-mcp` from single-query text-to-SQL into intent-driven, multi-source query orchestration with a first-class semantic layer.

Companion document: `docs/datamcp-p0-product-contract.md`.
Related note: `docs/datamcp-fsm-runtime-note.md`.

## 1. V1 Outcome (Concrete)

By the end of V1, `db-mcp` should reliably do this:

1. Accept one natural-language request.
2. Resolve intent against an org/domain semantic core (entities, metrics, rules, templates).
3. Compile a semantic meta-query plan (internal AST; Substrait optional later).
4. Declare expected cardinality (`ONE`/`MANY`) per meta-query node.
5. Submit the meta-query to a resolver/physical planner.
6. Validate cardinality expectations using AST + metadata + runtime checks.
7. Route physical subplans to connection-bound executors with existing policy gates.
8. Aggregate/merge fetched data into one canonical record stream.
9. Return a synthesized answer with explicit provenance and confidence.
10. Capture knowledge observations from execution and feed a governed promotion queue.

This is intentionally **text-to-query orchestration**, not only text-to-SQL generation.

## 2. Current Baseline in Repo

The repo already contains most foundation pieces:

- Connector abstraction and routing:
  - `packages/core/src/db_mcp/connectors/`
  - `packages/core/src/db_mcp/registry.py`
- Unified execution lifecycle and persistent execution state:
  - `packages/core/src/db_mcp/execution/models.py`
  - `packages/core/src/db_mcp/execution/engine.py`
  - `packages/core/src/db_mcp/execution/store.py`
- Tool surface for SQL and API execution:
  - `packages/core/src/db_mcp/tools/generation.py`
  - `packages/core/src/db_mcp/tools/api.py`
  - `packages/core/src/db_mcp/tools/database.py`
- Existing semantic artifacts:
  - `schema/descriptions.yaml`
  - `domain/model.md`
  - `metrics/catalog.yaml`
  - `instructions/sql_rules.md`
  - `examples/*.yaml`

Main gap: there is no explicit **semantic-core -> meta-query -> resolver -> executors -> aggregator** pipeline with a canonical typed record envelope and provenance contract.

## 3. V1 Design Constraints

1. Preserve existing tools (`run_sql`, `validate_sql`, `get_result`, `api_query`, `api_execute_sql`).
2. Add orchestration incrementally; do not break current single-connection behavior.
3. Keep business semantics above individual connections; treat connections as bindings/execution targets.
4. Prefer capability-driven routing over connector-type branching in prompt logic.
5. Keep Substrait optional in V1; use internal meta-query AST first.
6. Make all orchestration output traceable: source, query text, timing, confidence.
7. Allow partial answers when some routed subplans fail.
8. No auto-promotion of learned knowledge in V1; human approval is required.
9. Cardinality is declared at semantic planning time and enforced at execution time.

## 4. Proposed V1 Architecture in This Repo

### 4.1 New Core Contracts

Add typed contracts in `packages/models/src/db_mcp_models/`:

- `semantic.py`
  - `SemanticEntity`, `SemanticRelationship`, `SemanticMetric`, `SemanticRule`, `SemanticTemplate`
- `bindings.py`
  - `SemanticBinding`, `MetricBinding`, `EntityBinding`, `BindingCandidate`, `BindingConfidence`
- `meta_query.py`
  - `MetaQueryPlan`, `MetaQueryNode`, `MetaFilter`, `MetaMeasure`, `MetaJoin`, `ExpectedCardinality`
- `orchestration.py`
  - `ResolvedPlan`, `PhysicalSubqueryPlan`, `ExecutionDAG`, `AggregationPlan`, `AnswerPlan`, `CardinalityCheck`
- `record.py`
  - `CanonicalRecord`, `RecordField`, `RecordBatch`, `RecordProvenance`
- `knowledge.py`
  - `KnowledgeState`, `KnowledgeObservation`, `KnowledgeCandidate`, `KnowledgeConflict`, `KnowledgeDecision`

Design notes:

- Semantic contracts are connection-agnostic.
- Binding contracts explicitly map semantic objects to connection-local physical resources.
- Keep canonical values JSON-serializable for V1.
- Add optional `arrow_schema` and `arrow_ipc_path` fields for later Arrow-native transport.
- Include `confidence` and `lineage` in every returned batch.
- Confidence is a structured vector: `semantic`, `binding`, `execution`, `aggregation`, `knowledge_coverage`, `answer`.
- Each node and batch carries `expected_cardinality` and `observed_cardinality`.

### 4.2 New Runtime Modules (Core)

Add modules in `packages/core/src/db_mcp/`:

- `semantic/core_loader.py`
  - Load org/domain semantic core (entities, relationships, metrics, rules, templates).
- `semantic/bindings_loader.py`
  - Load connection bindings and resolve candidate mappings.
- `planner/meta_query.py`
  - Intent classification and compilation into `MetaQueryPlan`.
- `planner/cardinality.py`
  - Cardinality designation and validation (AST + schema/API metadata).
- `planner/resolver.py`
  - Resolve meta-query nodes into physical plans using bindings + capabilities.
- `planner/dag.py`
  - Build execution DAG and identify parallelizable stages.
- `orchestrator/engine.py`
  - End-to-end orchestration: meta-query -> resolved plan -> execution -> aggregation.
- `executors/router.py`
  - Route physical subplans to SQL/API/file executors per connection.
- `records/normalize.py`
  - Convert executor outputs into `CanonicalRecord` batches.
- `records/aggregator.py`
  - Deterministic join/union/enrich/post-aggregation across batches.
- `synthesis/answer.py`
  - Final natural language synthesis with provenance summary.
- `learning/events.py`
  - Emit knowledge observations from planner/resolver/executor/aggregator events.
- `learning/queue.py`
  - Persist candidates/conflicts and review status; no auto-promotion path in V1.

### 4.3 Tool Surface Changes

Keep existing tools as-is and add one orchestration-first tool:

- New tool (preferred): `answer_intent(intent, connection?, connections?, options?)`

Behavior:

1. Calls orchestrator.
2. Compiles a semantic meta-query from intent + semantic core.
3. Declares expected cardinality per query node (`ONE`/`MANY`).
4. Submits meta-query to resolver/planner for physical routing.
5. Executes routed subplans via existing `run_sql` / `api_execute_sql` paths.
6. Enforces cardinality checks on observed results.
7. Aggregates canonical record batches and returns:
   - `answer`
   - `records` (canonical output)
   - `provenance`
   - `confidence`
   - `execution_ids`
   - `meta_query`
   - `resolved_plan`
   - `knowledge_observations`
   - `result_shape` (expected/observed cardinality)

Compatibility:

- Existing `get_data` remains for MCP-sampling SQL plan generation.
- New `answer_intent` becomes the default semantic orchestrator path.

## 5. Phased Implementation Plan

## Phase 0: Hardening and Interface Baseline (1 week)

Deliverables:

1. Define canonical record/provenance model in `db_mcp_models`.
2. Define knowledge lifecycle model with states: `Observed`, `Candidate`, `Conflicted`, `Approved`, `Deprecated`.
3. Define confidence vector contract including `knowledge_coverage_confidence`.
4. Define cardinality model (`ONE`, `MANY`, `EMPTY`) and violation semantics.
5. Introduce no-op adapters from existing query results to canonical records.
6. Add feature flag: `DB_MCP_ENABLE_ORCHESTRATOR_V1=1`.

Repo changes:

- Add model files under `packages/models/src/db_mcp_models/`.
- Add thin normalization helpers under `packages/core/src/db_mcp/records/`.
- Add lifecycle model scaffolding under `packages/core/src/db_mcp/learning/`.
- No behavior changes to existing tools by default.

Exit criteria:

- Unit tests cover model validation, lifecycle states, and normalization from SQL/API/file results.
- Unit tests cover cardinality designation/enforcement semantics.

## Phase 1: Semantic Core + Binding Layer (1 week)

Deliverables:

1. Semantic core loader that reads org/domain semantic artifacts.
2. Binding loader that maps semantic objects to connection-local resources.
3. Normalized in-memory semantic graph + bindings index.
4. Load only `Approved` items for serving by default.
5. Load endpoint/entity cardinality hints where available.

Repo changes:

- `packages/core/src/db_mcp/semantic/core_loader.py`
- `packages/core/src/db_mcp/semantic/bindings_loader.py`
- Optional helper: `packages/core/src/db_mcp/semantic/index.py`

Exit criteria:

- Given an org/domain, loader returns deterministic semantic graph.
- Given a connection, binding resolver returns deterministic semantic mappings.
- Clear warnings when semantic core or bindings are missing/stale.
- Serving path ignores non-approved lifecycle states unless explicitly requested.
- Cardinality hints are available to planner from semantic templates/bindings.

## Phase 2: Meta-Query Planner (2 weeks)

Deliverables:

1. `MetaQueryPlan` generation:
   - identify metric/entity/time/filter intent
   - compile into semantic AST (no connection assumptions)
2. Validation rules for semantic completeness (missing entity/metric/template checks).
3. Meta-query explainability payload for debugging.
4. Planner emits ambiguity/low-confidence observations into learning event stream.
5. Planner designates expected cardinality for each node.

Repo changes:

- `packages/core/src/db_mcp/planner/meta_query.py`
- `packages/core/src/db_mcp/planner/cardinality.py`
- `packages/core/src/db_mcp/planner/validation.py`
- `packages/core/src/db_mcp/planner/explain.py`
- `packages/core/src/db_mcp/learning/events.py`

Exit criteria:

- Planner produces stable meta-queries for fixed inputs.
- Semantic validation errors are explicit and machine-readable.
- Ambiguity and low-confidence cases are persisted as observations.
- Cardinality designation is stable and explainable for fixed inputs.

## Phase 3: Resolver + Connection-Bound Execution (2 weeks)

Deliverables:

1. Resolver compiles meta-query into connection-specific `PhysicalSubqueryPlan`s.
2. Execution DAG supports parallel stages for independent subplans.
3. Standardized error handling to `ExecutionErrorCode`.
4. Partial-result semantics for non-fatal subplan failures.
5. Executor/resolver emit failed-binding and routing-failure observations.
6. Executor reports observed cardinality and violations.

Repo changes:

- `packages/core/src/db_mcp/orchestrator/engine.py`
- `packages/core/src/db_mcp/planner/resolver.py`
- `packages/core/src/db_mcp/executors/router.py`
- `packages/core/src/db_mcp/learning/events.py` (execution hooks)
- Integrate with `packages/core/src/db_mcp/execution/engine.py`
- Reuse existing policy checks in `execution/policy.py`

Exit criteria:

- Resolved plans route to expected connections/executors in deterministic tests.
- Multi-source executions return per-step execution metadata.
- Failures retain successful partial outputs with explicit status.
- Failed bindings/routing issues are persisted as candidates.
- `ONE` intents returning multiple rows produce explicit cardinality violations.

## Phase 4: Aggregation + Synthesis (1 week)

Deliverables:

1. Deterministic canonical aggregation layer (`join`, `union`, `enrich`, `post-agg`).
2. Final answer synthesis with provenance and confidence.
3. User-facing summary of contributing sources and caveats.
4. Aggregator emits merge/cardinality conflict observations.

Repo changes:

- `packages/core/src/db_mcp/records/aggregator.py`
- `packages/core/src/db_mcp/synthesis/answer.py`
- `packages/core/src/db_mcp/learning/events.py` (aggregation hooks)

Exit criteria:

- Output includes answer + machine-readable provenance contract.
- Confidence score degrades when semantic match/binding/routing confidence is low.
- Merge conflicts generate `Conflicted` knowledge items where applicable.
- Cardinality violations are reflected in `warnings` and confidence degradation.

## Phase 5: Tooling + Rollout (1 week)

Deliverables:

1. Register new tool in `server.py`.
2. Add docs and release notes.
3. Run staged rollout behind feature flag.
4. Expose knowledge review tools (`knowledge_status`, queue/promote/reject/diff/explain).
5. Expose cardinality explanation tooling for debugging.

Repo changes:

- `packages/core/src/db_mcp/server.py`
- `packages/core/src/db_mcp/tool_catalog.py` (category mapping)
- `docs/` updates and release note under `docs/releases/`

Exit criteria:

- E2E tests pass for single-source and multi-source orchestration paths.
- Existing tool behavior remains backward-compatible.
- Knowledge tools work with explicit human review; no auto-promotion path exists.
- Cardinality explain/debug path is available to users and agents.

## 6. Testing Strategy (Required)

Add tests before implementation for each phase (TDD):

- New model tests:
  - `packages/core/tests/test_orchestration_models.py`
  - `packages/core/tests/test_canonical_record_models.py`
  - `packages/core/tests/test_knowledge_lifecycle_models.py`
  - `packages/core/tests/test_cardinality_models.py`
- Semantic layer tests:
  - `packages/core/tests/test_semantic_core_loader.py`
  - `packages/core/tests/test_semantic_bindings_loader.py`
- Meta-query and resolver tests:
  - `packages/core/tests/test_meta_query_planner.py`
  - `packages/core/tests/test_meta_query_resolver.py`
- Cardinality tests:
  - `packages/core/tests/test_cardinality_designation.py`
  - `packages/core/tests/test_cardinality_enforcement.py`
- Learning loop tests:
  - `packages/core/tests/test_learning_event_triggers.py`
  - `packages/core/tests/test_knowledge_queue_workflow.py`
- Orchestrator tests:
  - `packages/core/tests/test_orchestrator_engine.py`
- Aggregator tests:
  - `packages/core/tests/test_records_aggregator.py`
- Tool-level tests:
  - `packages/core/tests/test_answer_intent_tool.py`
  - `packages/core/tests/test_knowledge_tools.py`
  - `packages/core/tests/test_cardinality_explain_tool.py`
- E2E tests:
  - `packages/core/tests/e2e/test_intent_orchestration_e2e.py`

Quality gates:

1. `cd packages/core && uv run ruff check . --fix`
2. `cd packages/core && uv run pytest tests/ -v`

## 7. Data Contracts and Storage (V1)

Semantic core artifacts (above connections):

- `~/.db-mcp/semantic/{org}/{domain}/entities.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/relationships.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/metrics.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/rules.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/templates.yaml`

Connection binding artifacts:

- `~/.db-mcp/connections/{name}/semantic_binding.yaml`
- existing connection-local schema artifacts remain as physical metadata sources.

Execution metadata extensions in execution store metadata payload:

- `intent_id`
- `meta_query_id`
- `subquery_id`
- `source_connection`
- `semantic_bindings` (entity/metric/rule names used)
- `merge_strategy`
- `expected_cardinality`
- `observed_cardinality`

Knowledge lifecycle storage:

- `~/.db-mcp/semantic/{org}/{domain}/knowledge/observations.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/knowledge/candidates.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/knowledge/conflicts.yaml`
- `~/.db-mcp/semantic/{org}/{domain}/knowledge/decisions.yaml`

## 8. Critical Decisions for V1 (Chosen)

1. **Internal AST first, Substrait later**
   - Build stable internal plan models now.
   - Add optional Substrait import/export in V1.5.

2. **Canonical JSON records first, Arrow transport second**
   - Keep immediate compatibility with MCP tool return shapes.
   - Attach optional Arrow payload metadata when available.

3. **Semantics above connections**
   - Semantic core is org/domain scoped.
   - Connections provide bindings and execution capabilities.

4. **Always return provenance**
   - Every answer includes source and transform lineage.

5. **Meta-query first, physical planning second**
   - Semantic compilation and physical routing are separate steps.

6. **Human-gated promotion in V1**
   - No automatic candidate promotion into approved semantic artifacts.

7. **Cardinality is a unifying access-pattern contract**
   - `ONE`/`MANY` is declared in semantic intent and validated through execution.

## 9. Delivery Sequence (Recommended)

1. Phase 0 + Phase 1 in one PR series.
2. Phase 2 meta-query planner in next PR series.
3. Phase 3 resolver/execution, then Phase 4 aggregation/synthesis.
4. Phase 5 registration/docs/release.

This sequence keeps risk isolated and avoids destabilizing existing SQL flows.

## 10. Risks and Mitigations

- Risk: planner nondeterminism from LLM variability.
  - Mitigation: structured plan schema + deterministic routing rules + snapshot tests.

- Risk: semantic artifacts drift from source schema.
  - Mitigation: freshness checks on bindings and schema-sync validations.

- Risk: merge errors due to key/type mismatches.
  - Mitigation: explicit join-key typing and strict aggregation validation.

- Risk: latency from fan-out execution.
  - Mitigation: execution DAG parallelism + per-subquery timeout + partial answers.

- Risk: knowledge queue noise overload.
  - Mitigation: strict trigger model, deduplication, and priority scoring before review.

- Risk: false positives/negatives in cardinality designation.
  - Mitigation: combine semantic hints + static AST analysis + metadata + runtime enforcement.

## 11. Definition of Done (V1)

V1 is done when all are true:

1. `answer_intent` works for single-source and multi-source intents.
2. Semantic resolution is org/domain scoped, with explicit connection bindings.
3. Outputs contain canonical records, provenance, confidence, and execution IDs.
4. Existing tools remain functional and backward compatible.
5. Test suite covers meta-query planner, resolver, executor routing, aggregator, and tool E2E.
6. Docs explain how to onboard semantic core/bindings and debug plans.
7. Knowledge lifecycle supports `Conflicted` state and evidence-backed `knowledge_explain`.
8. No auto-promotion exists in production code path.
9. Cardinality (`ONE`/`MANY`) is designated, validated, and surfaced in output contracts.
