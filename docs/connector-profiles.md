# Connector Profiles and Capability Matrix

## Why This Exists

`db-mcp` started as a SQL database tool, then expanded to API and file connectors.  
To keep CLI, UI, onboarding, and tool behavior consistent, we now treat `connector.yaml` as the
single source of truth with a first-class `profile` field.

## Connector Model

Two dimensions define behavior:

- `type`: connector implementation family (`sql`, `api`, `file`, `metabase`)
- `profile`: user-journey and capability preset

Capabilities are resolved in this order:

1. baseline defaults
2. type defaults
3. profile defaults
4. explicit `capabilities` overrides from `connector.yaml`

This keeps backward compatibility while enabling richer defaults for API/File/Hybrid flows.

## Versioned Connector Spec

`connector.yaml` now supports explicit versioning:

- `spec_version`: semantic version for connector contract compatibility (current: `1.0.0`)
- JSON Schema bundle path: `packages/core/contracts/connector/v1/`
- CLI validator: `db-mcp connector validate <path-to-connector.yaml>`

Example:

```yaml
spec_version: 1.0.0
type: api
profile: api_openapi
base_url: https://api.example.com/v1
auth:
  type: bearer
  token_env: API_TOKEN
```

Contract rules:

- major version mismatch is rejected
- profile/type combinations are validated (`api_openapi` only with `type: api`, etc.)
- extension profiles are allowed with `x-` prefix (for custom deployments)

## Supported Profiles

| Profile | Allowed Type(s) | Typical Source | Notes |
| --- | --- | --- | --- |
| `sql_db` | `sql` | Postgres/Trino/MySQL/etc | Full SQL workflow |
| `file_local` | `file` | CSV/Parquet/JSON | DuckDB over local files |
| `api_sql` | `api` | Dune-like SQL APIs | SQL over API transport |
| `api_openapi` | `api` | APIs with OpenAPI/Swagger | Endpoint discovery from spec |
| `api_probe` | `api` | Undocumented APIs | Heuristic endpoint probing |
| `hybrid_bi` | `api`, `metabase` | Superset/Metabase-style | SQL + dashboard/endpoint API |

## Example `connector.yaml`

### SQL API

```yaml
type: api
profile: api_sql
base_url: https://api.example.com/v1
auth:
  type: header
  token_env: API_KEY
  header_name: X-API-KEY
capabilities:
  sql_mode: api_async
```

### Generic API with OpenAPI

```yaml
type: api
profile: api_openapi
base_url: https://api.example.com/v1
auth:
  type: bearer
  token_env: API_TOKEN
```

### Local Files

```yaml
type: file
profile: file_local
directory: ./data
```

## CLI Visibility

`db-mcp status` now surfaces `type:profile` per connection and shows active capability highlights.
`db-mcp doctor --json` includes `connector_profile` in diagnostics payload.

## Community Catalog Direction

To support a community-driven catalog of reusable connector descriptors, we should keep
`connector.yaml` portable and add optional metadata:

```yaml
catalog:
  id: community/dune-mainnet
  version: 1.0.0
  source: github
  url: https://github.com/<org>/<repo>/path/connector.yaml
  checksum: sha256:<digest>
```

Design goals:

- deterministic imports (`id + version + checksum`)
- auditable provenance (`source + url`)
- safe updates (`version` pinning, explicit upgrade flow)
- local overrides allowed without breaking portability

## Phase 2 Follow-ups

- UI onboarding tracks by profile (`sql_db`, `api_openapi`, `api_probe`, `file_local`, `hybrid_bi`)
- profile-aware action queue and insights
- profile-specific doctor checks (auth/spec/probe/sync/sql)
- catalog import/export commands and trust policy
