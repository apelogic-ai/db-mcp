# Metrics & Dimensions Discovery

Extends the existing metrics layer (`metrics-layer.md`) with dimension modeling, automated discovery from vault material, and a management UI.

## Problem

The knowledge vault contains rich material for business metrics and dimensions:

- **Training examples** (31 in nova) — real SQL with `SUM(wifi_sub_count) AS dau`, `GROUP BY date, carrier`
- **Business rules** (100+ in nova) — "DAU stands for daily active users", "Price for 1 GB = 0.5 USD"
- **Schema descriptions** — typed columns across 50 tables (numeric = measures, varchar = dimensions, timestamp = temporal)

None of this is captured as structured metric/dimension definitions. The `Metric` model exists but has no dimension concept, `metrics/catalog.yaml` is empty, no MCP tools are registered, and there's no UI.

## What We're Building

| Component | Description |
|-----------|-------------|
| **Dimension model** | `Dimension`, `DimensionsCatalog` — typed dimensions (temporal, categorical, geographic, entity) |
| **Mining engine** | LLM-based extraction of metric/dimension candidates from vault material |
| **BICP endpoints** | List, approve, reject, add, edit, delete for metrics and dimensions |
| **UI page** | `/metrics` — two tabs: Candidates (mined) and Catalog (approved) |
| **File persistence** | `metrics/catalog.yaml` (metrics), `metrics/dimensions.yaml` (dimensions) |

## Data Flow

```
Vault Material                    Mining (LLM)              UI / Management
──────────────                    ────────────              ────────────────
training/examples/*.yaml  ──┐
                             ├──▶  Candidates  ──┬──▶  /metrics (Candidates tab)
instructions/business_rules ─┤     (in-memory)   │         ↓ approve / reject / edit
schema/descriptions.yaml  ──┘                    │     /metrics (Catalog tab)
                                                  │         ↓
                                                  └──▶  metrics/catalog.yaml
                                                        metrics/dimensions.yaml
```

## Dimension Model

Dimensions are the GROUP BY columns that slice metrics. Four types:

| Type | Examples | Detection Signal |
|------|----------|------------------|
| **temporal** | `date`, `created_at`, `call_time_min` | timestamp/date column types |
| **categorical** | `carrier`, `realm`, `venue_type`, `plan_name` | varchar columns in GROUP BY clauses |
| **geographic** | `city`, `state`, `zip_code` | location-related column names |
| **entity** | `subscriber_id`, `nas_identifier` | ID columns used in COUNT DISTINCT |

```python
class DimensionType(str, Enum):
    TEMPORAL = "temporal"
    CATEGORICAL = "categorical"
    GEOGRAPHIC = "geographic"
    ENTITY = "entity"

class Dimension(BaseModel):
    name: str                          # "carrier"
    display_name: str | None           # "Carrier"
    description: str
    type: DimensionType
    column: str                        # "cdr_agg_day.carrier"
    tables: list[str]                  # tables where this dimension exists
    values: list[str]                  # known values ["tmo", "helium_mobile"]
    synonyms: list[str]               # from business rules ["T-Mobile", "TMO"]
    created_at: datetime | None
    created_by: str | None             # "mined" | "manual"
```

The existing `Metric` model gains a `dimensions: list[str]` field — names of compatible dimensions.

## Mining Engine

`packages/core/src/db_mcp/metrics/mining.py`

### Inputs

1. **Training examples** — parse SQL for:
   - Aggregation functions → metric candidates (COUNT, SUM, AVG, MAX, MIN)
   - GROUP BY columns → dimension candidates
   - WHERE filters → required filters on metrics
   - Tables → metric table bindings

2. **Business rules** — parse for:
   - Metric definitions ("DAU stands for daily active users")
   - Calculation constants ("Price for 1 GB = 0.5 USD")
   - Synonym mappings ("T-Mobile, TMO are synonyms") → dimension value lists
   - Table routing ("use cdr_agg_day for per-subscriber info") → metric table bindings

3. **Schema descriptions** — classify columns by type:
   - Numeric columns (integer, double, decimal) → potential measures
   - Timestamp/date columns → temporal dimensions
   - Varchar columns appearing in GROUP BY → categorical dimensions

### Process

```python
async def mine_metrics_and_dimensions(connection_path: Path, ctx=None) -> dict:
    """
    1. Load examples, rules, schema from vault
    2. Build structured prompt with all material
    3. Ask LLM to identify:
       - Metrics: name, description, SQL template, tables, compatible dimensions
       - Dimensions: name, type, column, tables, known values
    4. Parse structured output (Pydantic models)
    5. Deduplicate and rank by confidence
    6. Return candidates
    """
```

### Output

```python
{
    "metric_candidates": [
        {
            "metric": { "name": "dau", "description": "Daily Active Users", ... },
            "confidence": 0.95,
            "source": "examples",
            "evidence": ["d35d0b66", "b6e90d25"]  # example IDs
        }
    ],
    "dimension_candidates": [
        {
            "dimension": { "name": "carrier", "type": "categorical", ... },
            "confidence": 0.9,
            "source": "examples",
            "evidence": ["GROUP BY carrier in 8 examples"]
        }
    ]
}
```

## BICP Endpoints

| Method | Params | Returns | Purpose |
|--------|--------|---------|---------|
| `metrics/list` | `{connection}` | `{metrics, dimensions}` | List approved catalog |
| `metrics/candidates` | `{connection}` | `{metric_candidates, dimension_candidates}` | Run mining |
| `metrics/approve` | `{connection, type, name, edits?}` | `{success}` | Approve candidate → catalog |
| `metrics/reject` | `{connection, type, name}` | `{success}` | Dismiss candidate |
| `metrics/add` | `{connection, type, data}` | `{success}` | Manual add |
| `metrics/update` | `{connection, type, name, data}` | `{success}` | Edit approved entry |
| `metrics/delete` | `{connection, type, name}` | `{success}` | Remove from catalog |

`type` is `"metric"` or `"dimension"`.

## UI Design

### `/metrics` Page

**Navigation**: Add "Metrics" between "Insights" and existing items in `layout.tsx`.

#### Tab: Candidates

```
┌─────────────────────────────────────────────────────────┐
│ Metrics & Dimensions                                     │
│ [Candidates] [Catalog]                    [Mine Vault ▶] │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ Metric Candidates (12 found)                             │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ★★★★★  dau — Daily Active Users                      │ │
│ │ SUM(wifi_sub_count) FROM daily_stats_cdrs            │ │
│ │ Dimensions: date, carrier                            │ │
│ │ Source: 4 training examples                          │ │
│ │                          [Approve] [Edit] [Reject]   │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ★★★★   traffic_volume — Data Traffic Volume (GB)     │ │
│ │ SUM(total_bytes) / 1e9 FROM cdr_agg_day              │ │
│ │ Dimensions: date, carrier, nas_identifier            │ │
│ │ Source: 6 training examples + business rules         │ │
│ │                          [Approve] [Edit] [Reject]   │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ Dimension Candidates (8 found)                           │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ carrier (categorical)                                │ │
│ │ Column: cdr_agg_day.carrier                          │ │
│ │ Values: tmo, helium_mobile, boost                    │ │
│ │ Synonyms: T-Mobile = TMO = tmo                      │ │
│ │                          [Approve] [Edit] [Reject]   │ │
│ └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### Tab: Catalog

```
┌─────────────────────────────────────────────────────────┐
│ Metrics & Dimensions                                     │
│ [Candidates] [Catalog]              [+ Metric] [+ Dim]  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ Approved Metrics (5)                                     │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ dau — Daily Active Users                     [Edit]  │ │
│ │ SUM(wifi_sub_count) FROM daily_stats_cdrs            │ │
│ │ Dimensions: date, carrier                            │ │
│ │ Tags: kpi, engagement                                │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ Approved Dimensions (4)                                  │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ date (temporal) — cdr_agg_day.date           [Edit]  │ │
│ │ carrier (categorical) — cdr_agg_day.carrier  [Edit]  │ │
│ │ city (geographic) — offload_att_directory.city [Edit] │ │
│ │ subscriber_id (entity) — cdr_agg_day.sub_id  [Edit]  │ │
│ └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## File Format

### `metrics/catalog.yaml` (existing, enhanced)

```yaml
version: "1.0.0"
provider_id: nova
metrics:
  - name: dau
    display_name: Daily Active Users
    description: Count of unique subscribers active on the Helium network per day
    sql: |
      SELECT {time_dimension}, COUNT(DISTINCT subscriber_id) AS dau
      FROM dwh.public.cdr_agg_day
      WHERE cdr_type = 'wifi'
        AND {time_dimension} >= {start_date}
        AND {time_dimension} < {end_date}
      GROUP BY 1
      ORDER BY 1
    tables:
      - dwh.public.cdr_agg_day
    dimensions:
      - date
      - carrier
    parameters:
      - name: time_dimension
        type: string
        default: date
      - name: start_date
        type: date
        required: true
      - name: end_date
        type: date
        required: true
    tags:
      - kpi
      - engagement
    created_at: "2026-01-30T10:00:00Z"
    created_by: mined
```

### `metrics/dimensions.yaml` (new)

```yaml
version: "1.0.0"
provider_id: nova
dimensions:
  - name: date
    display_name: Date
    description: Calendar date for daily aggregation
    type: temporal
    column: cdr_agg_day.date
    tables:
      - dwh.public.cdr_agg_day
      - dwh.public.daily_stats_cdrs
      - dwh.public.daily_stats_hh
    values: []
    synonyms: []

  - name: carrier
    display_name: Carrier
    description: Mobile network carrier
    type: categorical
    column: cdr_agg_day.carrier
    tables:
      - dwh.public.cdr_agg_day
      - dwh.public.daily_stats_cdrs
    values:
      - tmo
      - helium_mobile
      - boost
    synonyms:
      - "T-Mobile = TMO = tmo"
      - "Helium Mobile = helium"
```

## Implementation Order

1. Models & storage (Dimension, DimensionsCatalog, dimension CRUD)
2. BICP endpoints (list, add, delete, update — manual management)
3. UI — Catalog tab (view/add/edit/delete)
4. Mining engine (LLM distillation from vault)
5. BICP endpoint for mining (metrics/candidates)
6. UI — Candidates tab (mine, review, approve/reject)
7. Agent awareness (PROTOCOL.md, server instructions)
8. Lint, build, tests
