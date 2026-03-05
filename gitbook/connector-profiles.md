# Connector Profiles

db-mcp supports multiple connector types and profiles, giving you a consistent way to connect SQL databases, REST APIs, local files, and BI tools.

## Connector model

Two dimensions define how a connection behaves:

- **`type`**: the connector implementation family (`sql`, `api`, `file`, `metabase`)
- **`profile`**: a user-journey and capability preset within that type

Capabilities are resolved in this order:

1. Baseline defaults
2. Type defaults
3. Profile defaults
4. Explicit `capabilities` overrides from your `connector.yaml`

This keeps backward compatibility while enabling richer defaults for API, file, and hybrid flows.

## Supported profiles

| Profile | Allowed Type(s) | Typical Source | Notes |
|---|---|---|---|
| `sql_db` | `sql` | PostgreSQL, Trino, MySQL, ClickHouse, SQL Server | Full SQL workflow |
| `file_local` | `file` | CSV, Parquet, JSON files | DuckDB over local files |
| `api_sql` | `api` | Dune-like SQL APIs | SQL over API transport |
| `api_openapi` | `api` | APIs with OpenAPI/Swagger spec | Endpoint discovery from spec |
| `api_probe` | `api` | Undocumented APIs | Heuristic endpoint probing |
| `hybrid_bi` | `api`, `metabase` | Superset, Metabase | SQL + dashboard/endpoint API |

## `connector.yaml` basics

Every connection can have a `connector.yaml` that describes its type, profile, and behavior. For plain SQL connections, db-mcp can work without one, but adding it is recommended for consistent multi-connection behavior.

### Versioned contract

`connector.yaml` supports explicit versioning via `spec_version`:

- Current version: `1.0.0`
- Major version mismatch is rejected at load time
- Profile/type combinations are validated (e.g. `api_openapi` only with `type: api`)
- Extension profiles are allowed with `x-` prefix for custom deployments

### Validate a connector file

```bash
db-mcp connector validate ~/.db-mcp/connections/mydb/connector.yaml
```

Output on success:

```
Connector contract is valid: connector.yaml
spec_version: 1.0.0
type/profile: api/api_openapi
```

## Examples

### SQL database

```yaml
spec_version: 1.0.0
type: sql
profile: sql_db
dialect: postgresql
description: Primary analytics warehouse
```

### SQL-like API (Dune)

```yaml
spec_version: 1.0.0
type: api
profile: api_sql
base_url: https://api.dune.com/api/v1
auth:
  type: header
  token_env: API_KEY
  header_name: X-DUNE-API-KEY
capabilities:
  sql_mode: api_async
endpoints:
  - name: execute_sql
    path: /sql/execute
    method: POST
    body_mode: json
  - name: get_execution_status
    path: /execution/{execution_id}/status
    method: GET
  - name: get_execution_results
    path: /execution/{execution_id}/results
    method: GET
```

### REST API with OpenAPI

```yaml
spec_version: 1.0.0
type: api
profile: api_openapi
base_url: https://api.example.com/v1
auth:
  type: bearer
  token_env: API_TOKEN
```

### Local files (CSV/Parquet/JSON)

```yaml
spec_version: 1.0.0
type: file
profile: file_local
directory: ./data
description: Local analytics exports
```

### Hybrid BI (Superset/Metabase)

```yaml
spec_version: 1.0.0
type: api
profile: hybrid_bi
base_url: https://superset.example.com/api/v1
auth:
  type: bearer
  token_env: SUPERSET_TOKEN
capabilities:
  supports_sql: true
  supports_dashboard_api: true
```

## CLI visibility

- `db-mcp status` surfaces `type:profile` per connection and shows active capability highlights
- `db-mcp doctor --json` includes `connector_profile` in its diagnostics payload
- `db-mcp connector validate <path>` validates a connector file against the versioned contract schema

## Capability defaults by type

| Capability | `sql` | `api` | `file` | `metabase` |
|---|---|---|---|---|
| `supports_sql` | ✅ | ❌ | ✅ | ✅ |
| `supports_validate_sql` | ✅ | ❌ | ✅ | ❌ |
| `supports_async_jobs` | ✅ | ❌ | ✅ | ❌ |
| `supports_endpoint_discovery` | ❌ | ✅ | ❌ | ✅ |
| `supports_file_scan` | ❌ | ❌ | ✅ | ❌ |
| `supports_dashboard_api` | ❌ | ❌ | ❌ | ✅ |

Explicit `capabilities` in your `connector.yaml` always override these defaults.

Related docs:

- [Install and Configuration](install-and-configuration.md)
- [Tools Reference](tools-reference.md)
- [Advanced Topics](advanced-topics.md)
