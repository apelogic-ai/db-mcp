# DataMCP FSM Runtime Note

**Status**: Pencil draft  
**Date**: 2026-03-07  
**Intent**: Reframe DataMCP internally as a deterministic query orchestration + knowledge mining FSM.

## Why this framing

DataMCP is evolving beyond a passive query tool. The behavior now maps naturally to a state machine:

1. Intake and intent resolution
2. Semantic planning and physical routing
3. Execution and aggregation
4. Confidence/provenance emission
5. Continuous knowledge accumulation

This is effectively an internal data-agent runtime with controlled interfaces.

## Core FSM (serving path)

1. `INTAKE`
2. `SEMANTIC_RESOLVE`
3. `META_QUERY_PLAN`
4. `BINDING_RESOLVE`
5. `EXECUTE`
6. `AGGREGATE`
7. `RESPOND`

Terminal states:

1. `SUCCESS`
2. `PARTIAL`
3. `ERROR`

Cross-cutting checks in-state:

1. Policy gates
2. Cardinality validation (`ONE`/`MANY`)
3. Budget/latency thresholds

## Knowledge FSM (side loop)

1. `OBSERVED`
2. `CANDIDATE`
3. `CONFLICTED`
4. `APPROVED`
5. `DEPRECATED`

Hard gate (V1): no auto-promotion. Human approval required for `APPROVED`.

## Interface strategy

One engine, multiple adapters:

1. **MCP adapter** for external agents (Claude Code, etc.)
   - Default: `answer_intent`, `get_result`, knowledge review tools
   - Expert mode: direct query tools
2. **ACP/native adapter** for engineers/scientists
   - Programmatic orchestration, CI checks, notebook workflows, batch evaluation

Rule: interfaces differ; orchestration logic does not.

## Proposed near-term implications

1. Treat planner/resolver/executor as explicit FSM stages in code and traces.
2. Persist state transitions as audit events for replay/debug.
3. Keep `answer_intent` as primary northbound contract.
4. Keep direct SQL/API tools behind explicit expert gating.
