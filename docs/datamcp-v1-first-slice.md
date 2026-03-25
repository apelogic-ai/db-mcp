# DataMCP V1 First Slice

**Status**: In progress  
**Date**: 2026-03-23  
**Branch**: `codex/semantic-ir-first-slice`

## Goal

Land the first executable semantic-layer slice without rewriting the whole query path.

This slice should prove three things:

1. `db-mcp` can own a typed semantic plan at runtime.
2. The semantic plan can deterministically resolve to an execution plan.
3. The execution plan can reuse existing policy-checked execution paths.

## Scope

Single-connection, metric-first orchestration:

1. Load approved metrics and dimensions from the current connection vault.
2. Resolve an intent to one approved metric deterministically.
3. Compile a typed `MetaQueryPlan`.
4. Resolve that plan to one connection-bound metric execution plan.
5. Execute the metric via the existing `run_sql` path.
6. Return machine-readable `meta_query`, `resolved_plan`, `provenance`, `confidence`, and `result_shape`.

## Explicit Non-Goals

This slice does **not** attempt to do any of the following:

1. Multi-source routing or aggregation.
2. Generic NL-to-SQL for arbitrary warehouse questions.
3. Unreviewed semantic promotion.
4. Full semantic-core storage above connections.
5. Dimension-aware metric rewrites or join synthesis.

## Contracts To Add Now

### Shared models

1. `ExpectedCardinality` / `ObservedCardinality`
2. `MetaMeasure`
3. `MetaDimension`
4. `MetaQueryPlan`
5. `MetricExecutionPlan`
6. `ConfidenceVector`
7. `ResultShape`

### Runtime modules

1. `semantic/core_loader.py`
2. `planner/meta_query.py`
3. `orchestrator/engine.py`
4. `tools/intent.py`

## Deterministic Resolution Rules

For this slice:

1. Only approved metrics are considered.
2. Metric matching is lexical and deterministic:
   - metric `name`
   - metric `display_name`
3. Dimensions may be detected, but if the query requires dimension-aware compilation the tool returns a structured error instead of guessing SQL.
4. Required metric parameters must be passed explicitly in `options.metric_parameters`.

## Northbound Tool

Add:

`answer_intent(intent, connection, options?)`

`options` for this slice:

```json
{
  "metric_parameters": {
    "start_date": "'2026-01-01'",
    "end_date": "'2026-02-01'"
  }
}
```

## Success Criteria

This slice is done when:

1. `answer_intent` can execute an approved metric on one connection.
2. Output includes `meta_query`, `resolved_plan`, `provenance`, `confidence`, `result_shape`.
3. Unknown metrics fail with structured resolution errors and candidate hints.
4. Missing metric parameters fail before SQL execution.
5. Existing `run_sql` remains the only execution path used underneath.
