# Playground Benchmark Pack

This folder defines benchmark cases for the `playground` connection when using
`db-mcp-benchmark`.

Each case in `cases.yaml` is:

- connection-specific
- scored deterministically from `gold_sql`
- intended to compare Claude Code with `db-mcp` attached versus a raw DSN baseline

Run against the playground connection with:

```bash
db-mcp-benchmark preflight --connection playground
db-mcp-benchmark run --connection playground --model <exact-claude-model-id>
```

For the semantic metric-first slice, run the dedicated pack and scenario:

```bash
db-mcp-benchmark run \
  --connection playground \
  --case-pack cases_semantic.yaml \
  --scenario answer_intent \
  --model <exact-claude-model-id>
```
