# DataMCP Semantic Importer Contract

**Status**: Draft  
**Date**: 2026-03-23  
**Intent**: Turn benchmark packs and connection knowledge into candidate executable semantics.

Related:
- `docs/datamcp-p0-product-contract.md`
- `docs/datamcp-fsm-runtime-note.md`
- `docs/datamcp-v1-first-slice.md`

## 1. Goal

The semantic importer exists to bootstrap a connection from:

1. existing benchmark gold queries,
2. business rules,
3. domain model text,
4. approved examples,
5. schema descriptions,

into candidate semantic artifacts that the `answer_intent` runtime can execute.

This is not a generic NL-to-SQL feature. It is a governed synthesis pipeline:

`connection artifacts -> candidate metrics/bindings -> review -> approved semantic serving`

## 2. Why It Exists

The Nova exercise proved a practical path:

1. Gold SQL is good enough to derive executable bindings.
2. Business rules and examples are good enough to derive logical names and parameter semantics.
3. A small synthesized metric layer can materially outperform prompt-only planning on a real connection.

The importer productizes that path so new connections can be bootstrapped repeatably instead of by hand.

## 3. Scope

### In scope for V1

1. Single-connection import only.
2. Benchmark-pack-driven candidate generation.
3. Metric-first artifacts only:
   - `metrics/catalog.yaml`
   - `metrics/bindings.yaml`
   - `metrics/dimensions.yaml` when confidently derivable
4. Semantic benchmark pack generation for `answer_intent`.
5. Candidate output only by default.

### Out of scope for V1

1. Multi-connection semantic-core synthesis.
2. Full ontology/entity graph generation.
3. Automatic promotion to approved serving artifacts.
4. Arbitrary join inference from free-form examples.
5. Non-benchmark-first mining from traces as the primary path.

## 4. Northbound Contract

Proposed northbound entrypoint:

`metrics_bootstrap_from_benchmark(connection, case_pack?, options?)`

Optional CLI wrapper:

`db-mcp metrics bootstrap --connection <name> --case-pack <file>`

Optional MCP tool wrapper later:

`metrics_bootstrap_from_benchmark`

The importer should be callable from:

1. CLI
2. MCP
3. batch/eval code

using one shared implementation.

## 5. Inputs

Required inputs:

1. `connection`
2. `case_pack`
   - default: connection-local `benchmark/cases.yaml`
   - optional override: `benchmark/cases_full.yaml` or another pack

Optional evidence sources:

1. `instructions/business_rules.yaml`
2. `domain/model.md`
3. `examples/*.yaml`
4. `schema/descriptions.yaml`
5. existing `metrics/*.yaml` if present

Options contract:

```json
{
  "emit_mode": "candidate|approved|temp_overlay",
  "target_root": "optional output directory",
  "max_cases": 50,
  "infer_dimensions": true,
  "infer_metric_parameters": true,
  "generate_semantic_case_pack": true,
  "reuse_existing_metrics": true,
  "strict_sql_parsing": true
}
```

### Input Normalization Rules

1. Benchmark case IDs are stable identifiers, not metric names.
2. Gold SQL is executable truth for binding extraction.
3. Business rules override ambiguous phrasing in prompts.
4. Existing approved metrics win over newly inferred duplicates.

## 6. Outputs

Primary artifacts:

1. `metrics/catalog.yaml`
2. `metrics/bindings.yaml`
3. `metrics/dimensions.yaml`
4. `benchmark/cases_semantic.yaml`

Secondary machine-readable report:

`metrics/import_report.json`

Suggested report contract:

```json
{
  "connection": "nova",
  "source_case_pack": "benchmark/cases.yaml",
  "cases_seen": 10,
  "clusters_created": 8,
  "metrics_created": 8,
  "dimensions_created": 0,
  "cases_grouped": {
    "total_data_traffic_tb": ["nova_q01", "nova_q02", "nova_q03"]
  },
  "unsupported_cases": [],
  "ambiguous_cases": [],
  "warnings": [],
  "evidence_used": {
    "business_rules": true,
    "domain_model": true,
    "examples": 15,
    "schema_descriptions": true
  }
}
```

Output policy:

1. Default output status is `candidate`.
2. `approved` output requires explicit operator request.
3. `temp_overlay` writes into an alternate root for evaluation-only runs.

## 7. Clustering Heuristics

The core problem is not writing files. It is deciding when multiple benchmark questions describe one reusable metric.

The importer should cluster cases into reusable metrics using the following precedence.

### 7.1 Physical equivalence

Two cases are strong candidates for one metric when they share:

1. the same source table family,
2. the same aggregate expression,
3. the same business unit conversion,
4. the same result shape.

Example:

`SUM(wifi_total_bytes) / 1099511627776.0`

on `dwh.public.daily_stats_cdrs` should collapse into one logical metric even if one case is 7-day and another is 30-day.

### 7.2 Window parameterization

Cases should become one reusable metric when they differ only by:

1. date literals,
2. window width,
3. inclusive end date phrasing,
4. one-day vs N-day window.

These differences should map to:

1. `time_context`
2. metric parameters like `start_date`, `end_date`

### 7.3 Business-semantic naming

Metric names should be chosen from semantic evidence in this order:

1. explicit business rules vocabulary,
2. domain model terminology,
3. validated example phrasing,
4. benchmark prompt wording,
5. fallback SQL-expression-derived naming.

The importer should prefer names like:

`total_data_traffic_tb`

over question IDs like:

`nova_q02`

### 7.4 Result-shape separation

Cases should **not** be clustered together if they differ in logical answer shape:

1. scalar total
2. grouped rowset
3. argmax/argmin returning a date
4. top-N list

Example:

`total_data_traffic_tb`

must stay separate from:

`max_daily_traffic_date`

even though both depend on daily traffic.

### 7.5 Table-selection fidelity

Business rules about canonical tables are hard constraints.

If two cases use different table families because the rules demand it, they should not be collapsed into one metric.

Example:

1. general Helium network traffic -> `daily_stats_cdrs`
2. rewarded vs unrewarded traffic -> `daily_stats_hh`

These are distinct metrics even if both involve bytes.

### 7.6 Unsupported-case fallback

If a case cannot be safely clustered into a reusable metric, the importer may emit:

1. a one-case metric candidate, or
2. an unsupported-case report entry

but it must not pretend the case generalized when it did not.

## 8. Derived Semantic Objects

### Metric

Derived from:

1. clustered benchmark prompts,
2. normalized gold SQL,
3. business rules and examples.

Must include:

1. `name`
2. `display_name`
3. `description`
4. `parameters`
5. `tags`
6. `tables`
7. `status`

### Binding

Derived primarily from gold SQL.

Must include:

1. `metric_name`
2. `sql`
3. `tables`
4. dimension bindings when safely derivable

### Dimension

Derived only when the evidence is strong:

1. grouped benchmark SQL,
2. benchmark prompt phrasing,
3. validated examples,
4. glossary/business-rule aliases.

V1 should bias toward under-generation here.

## 9. First Implementation Slice

### Goal

Land a benchmark-first importer that can synthesize candidate semantics for scalar metrics and simple grouped rowsets.

### Proposed module layout

1. `packages/core/src/db_mcp/importer/benchmark_semantics.py`
2. `packages/core/src/db_mcp/importer/sql_patterns.py`
3. `packages/core/src/db_mcp/importer/evidence.py`
4. `packages/core/src/db_mcp/tools/metrics_bootstrap.py`

Shared models if needed:

1. `packages/models/src/db_mcp_models/importer.py`

### V1 supported pattern families

1. scalar aggregate over a date window
2. scalar aggregate over one day
3. argmax/argmin date over grouped daily aggregate
4. grouped aggregate rowset with one grouping key

### V1 unsupported pattern families

1. multi-step join-heavy benchmark questions
2. complex CASE-driven business logic without stable naming evidence
3. top-N entity lists with multiple dimensions
4. questions requiring free-form filter extraction from prompt text alone

### V1 output behavior

1. write candidate semantic artifacts
2. emit semantic case pack
3. run eval immediately if requested
4. return import report with grouped vs unsupported cases

## 10. Proposed Runtime Workflow

1. Load benchmark cases.
2. Parse gold SQL into normalized pattern sketches.
3. Collect vocabulary from business rules, domain model, examples, schema descriptions.
4. Cluster cases into candidate reusable metrics.
5. Synthesize metric catalog entries.
6. Synthesize binding entries.
7. Optionally synthesize dimensions.
8. Generate `cases_semantic.yaml` with explicit `answer_intent_options`.
9. Write import report.
10. Optionally run semantic benchmark against the generated overlay.

## 11. Review and Promotion Contract

The importer must not bypass the governed knowledge lifecycle.

Required lifecycle:

1. `imported` -> candidate files written
2. `reviewed` -> operator inspects generated metrics/bindings/report
3. `approved` -> artifacts promoted into serving path

Suggested helper tools later:

1. `metrics_bootstrap_report`
2. `metrics_bootstrap_promote`
3. `metrics_bootstrap_diff`
4. `metrics_bootstrap_validate`

## 12. Nova As Reference Case

Nova is the canonical pilot for V1 because it contains:

1. benchmark packs,
2. strong business rules,
3. domain model text,
4. validated examples,
5. heterogeneous but still pattern-rich analytical questions.

The manual Nova overlay demonstrated that benchmark cases can collapse into reusable semantics such as:

1. `total_data_traffic_tb`
2. `max_daily_traffic_date`
3. `max_daily_dau`
4. `users_served`
5. `rewarded_traffic_tb`
6. `unrewarded_traffic_gb`
7. `brownfield_sites_with_traffic`
8. `brownfield_called_station_ids_with_traffic`

This is the baseline the importer should reproduce automatically.

## 13. Acceptance Criteria

The first importer slice is successful when:

1. it can bootstrap a temp semantic overlay from Nova benchmark artifacts,
2. it groups related cases into reusable metrics instead of one metric per question where possible,
3. it emits a valid `metrics/catalog.yaml` and `metrics/bindings.yaml`,
4. the generated `cases_semantic.yaml` runs under `answer_intent`,
5. benchmark accuracy on the active Nova slice is not materially worse than the hand-authored overlay,
6. unsupported and ambiguous cases are reported explicitly.

## 14. Non-Goals

This importer should not:

1. claim to infer a full enterprise semantic layer from benchmarks alone,
2. replace analyst review,
3. mutate approved artifacts silently,
4. hide unsupported benchmark questions behind over-generalized metrics.
