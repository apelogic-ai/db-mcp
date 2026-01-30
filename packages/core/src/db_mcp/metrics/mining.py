"""Metrics and dimensions mining — extract candidates from vault material.

Reads training examples, business rules, and schema descriptions to identify
metric and dimension candidates using heuristic analysis of SQL patterns.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from db_mcp_models.metrics import (
    Dimension,
    DimensionCandidate,
    DimensionType,
    Metric,
    MetricCandidate,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Vault material loaders
# =============================================================================


def _load_examples(connection_path: Path) -> list[dict]:
    """Load training examples from the vault."""
    examples_dir = connection_path / "training" / "examples"
    examples = []
    if not examples_dir.exists():
        return examples

    for f in sorted(examples_dir.glob("*.yaml")):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
                if data and isinstance(data, dict):
                    data["_file"] = f.name
                    examples.append(data)
        except Exception:
            continue
    return examples


def _load_rules(connection_path: Path) -> list[str]:
    """Load business rules from the vault."""
    rules_file = connection_path / "instructions" / "business_rules.yaml"
    if not rules_file.exists():
        return []

    try:
        with open(rules_file) as f:
            data = yaml.safe_load(f)
        if data and isinstance(data, dict):
            rules = data.get("rules", [])
            return [r for r in rules if isinstance(r, str)]
    except Exception:
        return []
    return []


def _load_schema(connection_path: Path) -> dict:
    """Load schema descriptions from the vault."""
    schema_file = connection_path / "schema" / "descriptions.yaml"
    if not schema_file.exists():
        return {}

    try:
        with open(schema_file) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# =============================================================================
# SQL pattern analysis
# =============================================================================

# Aggregation function patterns
_AGG_PATTERN = re.compile(
    r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(DISTINCT\s+)?(.+?)\s*\)",
    re.IGNORECASE,
)

# GROUP BY extraction
_GROUP_BY_PATTERN = re.compile(
    r"\bGROUP\s+BY\s+(.+?)(?:\bORDER\b|\bHAVING\b|\bLIMIT\b|\bWINDOW\b|;|$)",
    re.IGNORECASE | re.DOTALL,
)

# FROM table extraction
_FROM_PATTERN = re.compile(
    r"\bFROM\s+([^\s,(]+)",
    re.IGNORECASE,
)

# Date/time column indicators
_TEMPORAL_INDICATORS = {
    "date",
    "day",
    "month",
    "year",
    "week",
    "quarter",
    "hour",
    "minute",
    "timestamp",
    "created_at",
    "updated_at",
    "time",
    "period",
}

# Geographic column indicators
_GEO_INDICATORS = {
    "city",
    "state",
    "country",
    "region",
    "zip",
    "zipcode",
    "postal",
    "latitude",
    "longitude",
    "lat",
    "lng",
    "lon",
    "geo",
    "location",
    "address",
    "county",
}

# Entity ID indicators
_ENTITY_INDICATORS = {
    "id",
    "user_id",
    "account_id",
    "customer_id",
    "subscriber_id",
    "session_id",
    "device_id",
    "nas_id",
    "provider_id",
}


def _classify_dimension_type(col_name: str, col_type: str = "") -> DimensionType:
    """Classify a column as temporal, geographic, categorical, or entity."""
    name_lower = col_name.lower()
    type_lower = col_type.lower()

    # Check type first
    if any(t in type_lower for t in ["date", "timestamp", "time"]):
        return DimensionType.TEMPORAL

    # Check name patterns
    name_parts = set(re.split(r"[_.\s]", name_lower))

    if name_parts & _TEMPORAL_INDICATORS:
        return DimensionType.TEMPORAL
    if name_parts & _GEO_INDICATORS:
        return DimensionType.GEOGRAPHIC
    if name_lower.endswith("_id") or name_parts & _ENTITY_INDICATORS:
        return DimensionType.ENTITY

    return DimensionType.CATEGORICAL


# Semantic category keyword maps — order matters (first match wins)
_SEMANTIC_CATEGORIES: list[tuple[str, set[str]]] = [
    (
        "Time",
        {
            "date",
            "day",
            "month",
            "year",
            "week",
            "quarter",
            "hour",
            "minute",
            "timestamp",
            "time",
            "period",
            "epoch",
            "interval",
            "duration",
            "created",
            "updated",
            "inserted",
            "modified",
            "started",
            "ended",
            "scheduled",
            "expires",
            "deadline",
        },
    ),
    (
        "Location",
        {
            "city",
            "state",
            "country",
            "region",
            "zip",
            "zipcode",
            "postal",
            "latitude",
            "longitude",
            "lat",
            "lng",
            "lon",
            "geo",
            "location",
            "address",
            "county",
            "continent",
            "province",
            "territory",
            "coords",
            "coordinates",
            "place",
            "area",
            "zone",
            "district",
        },
    ),
    (
        "User",
        {
            "user",
            "customer",
            "subscriber",
            "member",
            "account",
            "owner",
            "author",
            "creator",
            "person",
            "contact",
            "profile",
            "tenant",
            "org",
            "organization",
            "company",
            "team",
            "group",
        },
    ),
    (
        "Device",
        {
            "device",
            "hardware",
            "model",
            "manufacturer",
            "firmware",
            "os",
            "platform",
            "browser",
            "client",
            "agent",
            "terminal",
            "phone",
            "mobile",
            "tablet",
            "desktop",
            "sensor",
            "ap",
            "access",
            "endpoint",
            "mac",
            "imei",
            "serial",
        },
    ),
    (
        "Network",
        {
            "network",
            "carrier",
            "provider",
            "operator",
            "ssid",
            "bssid",
            "ip",
            "subnet",
            "vlan",
            "port",
            "protocol",
            "bandwidth",
            "frequency",
            "channel",
            "signal",
            "rssi",
            "snr",
            "nas",
            "radio",
            "wifi",
            "cellular",
            "lte",
            "5g",
        },
    ),
    (
        "Product",
        {
            "product",
            "item",
            "sku",
            "catalog",
            "category",
            "brand",
            "plan",
            "tier",
            "subscription",
            "package",
            "service",
            "offering",
            "pricing",
            "price",
            "cost",
            "rate",
            "fee",
        },
    ),
    (
        "Status",
        {
            "status",
            "state",
            "phase",
            "stage",
            "result",
            "outcome",
            "error",
            "code",
            "reason",
            "flag",
            "enabled",
            "active",
            "type",
            "kind",
            "class",
            "level",
            "priority",
            "severity",
        },
    ),
    (
        "Measurement",
        {
            "count",
            "total",
            "sum",
            "avg",
            "average",
            "mean",
            "median",
            "min",
            "max",
            "rate",
            "ratio",
            "percent",
            "percentage",
            "score",
            "index",
            "value",
            "amount",
            "quantity",
            "volume",
            "size",
            "length",
            "width",
            "height",
            "weight",
            "speed",
            "utilization",
            "bitrate",
            "throughput",
            "latency",
            "noise",
            "loss",
            "frame",
            "agg",
            "aggregat",
        },
    ),
]


def _classify_semantic_category(col_name: str, col_type: str = "") -> str:
    """Classify a column into a semantic business category."""
    name_lower = col_name.lower()
    name_parts = set(re.split(r"[_.\s]", name_lower))

    # Check column type for time hints
    type_lower = col_type.lower()
    if any(t in type_lower for t in ["date", "timestamp", "time"]):
        return "Time"

    # Match against category keyword sets
    for category, keywords in _SEMANTIC_CATEGORIES:
        if name_parts & keywords:
            return category

    return "Other"


def _extract_agg_name(agg_func: str, column: str, intent: str = "") -> str:
    """Generate a metric name from aggregation function and column."""
    # Clean column reference
    col = column.split(".")[-1].strip().strip(")")
    if col == "*":
        col = "records"

    # Build name
    func_lower = agg_func.lower()
    name = f"{func_lower}_{col}"

    # Clean up
    name = re.sub(r"[^a-z0-9_]", "_", name.lower())
    name = re.sub(r"_+", "_", name).strip("_")

    return name


def _extract_display_name(name: str) -> str:
    """Convert snake_case name to display name."""
    return name.replace("_", " ").title()


# =============================================================================
# Mining from examples
# =============================================================================


def _mine_from_examples(
    examples: list[dict],
) -> tuple[list[MetricCandidate], list[DimensionCandidate]]:
    """Extract metric and dimension candidates from training examples."""
    metric_candidates: list[MetricCandidate] = []
    dimension_candidates: list[DimensionCandidate] = []

    # Track seen names to deduplicate
    seen_metrics: set[str] = set()
    seen_dimensions: set[str] = set()

    for ex in examples:
        sql = ex.get("sql", "")
        intent = ex.get("natural_language", "")
        file_name = ex.get("_file", "")
        tags = ex.get("tags", [])

        if not sql:
            continue

        # Extract tables
        tables = [m.group(1).split(".")[-1] for m in _FROM_PATTERN.finditer(sql)]

        # Find aggregations → metrics
        for match in _AGG_PATTERN.finditer(sql):
            agg_func = match.group(1)
            distinct = match.group(2) or ""
            agg_col = match.group(3).strip()

            name = _extract_agg_name(agg_func, agg_col, intent)
            if name in seen_metrics:
                continue
            seen_metrics.add(name)

            # Build a clean SQL snippet
            description = intent if intent else f"{agg_func}({distinct}{agg_col})"

            metric = Metric(
                name=name,
                display_name=_extract_display_name(name),
                description=description,
                sql=sql,
                tables=tables,
                tags=tags if tags else [],
            )

            metric_candidates.append(
                MetricCandidate(
                    metric=metric,
                    confidence=0.7 if intent else 0.5,
                    source="examples",
                    evidence=[file_name] if file_name else [],
                )
            )

        # Find GROUP BY columns → dimensions
        group_match = _GROUP_BY_PATTERN.search(sql)
        if group_match:
            group_cols_raw = group_match.group(1)
            # Split by comma, handle expressions
            group_cols = [
                c.strip()
                for c in group_cols_raw.split(",")
                if c.strip() and not c.strip().startswith("(")
            ]

            for col_ref in group_cols:
                # Skip numeric references like GROUP BY 1, 2
                if col_ref.strip().isdigit():
                    continue

                col_name = col_ref.split(".")[-1].strip()
                # Skip function calls
                if "(" in col_name:
                    continue

                dim_name = re.sub(r"[^a-z0-9_]", "_", col_name.lower()).strip("_")
                if not dim_name or dim_name in seen_dimensions:
                    continue
                seen_dimensions.add(dim_name)

                dim_type = _classify_dimension_type(col_name)

                dimension = Dimension(
                    name=dim_name,
                    display_name=_extract_display_name(dim_name),
                    description=f"Dimension from GROUP BY in: {intent[:80]}" if intent else "",
                    type=dim_type,
                    column=col_ref.strip(),
                    tables=tables,
                )

                dimension_candidates.append(
                    DimensionCandidate(
                        dimension=dimension,
                        confidence=0.6,
                        source="examples",
                        evidence=[file_name] if file_name else [],
                        category=_classify_semantic_category(col_name),
                    )
                )

    return metric_candidates, dimension_candidates


# =============================================================================
# Mining from business rules
# =============================================================================


def _mine_from_rules(
    rules: list[str],
) -> tuple[list[MetricCandidate], list[DimensionCandidate]]:
    """Extract metric and dimension hints from business rules."""
    metric_candidates: list[MetricCandidate] = []
    dimension_candidates: list[DimensionCandidate] = []

    # Patterns that suggest metric definitions in rules
    metric_keywords = re.compile(
        r"\b(metric|kpi|measure|count|total|average|sum|rate|ratio|percentage)\b",
        re.IGNORECASE,
    )

    # Patterns that suggest dimension/category definitions
    dimension_keywords = re.compile(
        r"\b(dimension|category|group|segment|type|class|tier|level|carrier|vendor)\b",
        re.IGNORECASE,
    )

    # Common SQL/English words that look like uppercase names but aren't metrics
    _NAME_STOPWORDS = {
        "MUST",
        "NEVER",
        "ALWAYS",
        "ONLY",
        "NOT",
        "AND",
        "BUT",
        "THE",
        "FOR",
        "USE",
        "ALL",
        "ANY",
        "ARE",
        "HAS",
        "HAVE",
        "WILL",
        "FROM",
        "INTO",
        "WITH",
        "THAT",
        "THIS",
        "WHEN",
        "WHERE",
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "DROP",
        "ALTER",
        "TABLE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "CROSS",
        "GROUP",
        "ORDER",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "UNION",
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "DISTINCT",
        "ASC",
        "DESC",
        "NULL",
        "TRUE",
        "FALSE",
        "CASE",
        "THEN",
        "ELSE",
        "END",
        "LIKE",
        "BETWEEN",
        "EXISTS",
        "VALUES",
        "SET",
        "ADD",
    }

    for rule in rules:
        # Check if rule defines a metric
        if metric_keywords.search(rule):
            # Try to extract a name from the rule
            # e.g. "DAU is defined as..." or "Calculate monthly_revenue by..."
            # Find all uppercase names and pick the first one that isn't a stopword
            name = None
            for m in re.finditer(r"\b([A-Z][A-Z0-9_]{2,})\b", rule):
                candidate = m.group(1)
                if candidate not in _NAME_STOPWORDS:
                    name = candidate.lower()
                    break

            if name:
                metric = Metric(
                    name=name,
                    display_name=_extract_display_name(name),
                    description=rule[:200],
                    sql="-- Extracted from business rule, SQL needs to be defined",
                )

                metric_candidates.append(
                    MetricCandidate(
                        metric=metric,
                        confidence=0.4,
                        source="rules",
                        evidence=[rule[:100]],
                    )
                )

        # Check if rule mentions dimension concepts
        if dimension_keywords.search(rule):
            # Look for quoted values or explicit column references
            values_match = re.findall(r'"([^"]+)"', rule)
            col_match = re.search(r"\b(\w+\.\w+)\b", rule)

            if col_match:
                col_ref = col_match.group(1)
                col_name = col_ref.split(".")[-1]
                dim_name = re.sub(r"[^a-z0-9_]", "_", col_name.lower()).strip("_")

                dimension = Dimension(
                    name=dim_name,
                    display_name=_extract_display_name(dim_name),
                    description=rule[:200],
                    type=_classify_dimension_type(col_name),
                    column=col_ref,
                    values=values_match[:10],
                )

                dimension_candidates.append(
                    DimensionCandidate(
                        dimension=dimension,
                        confidence=0.5,
                        source="rules",
                        evidence=[rule[:100]],
                        category=_classify_semantic_category(col_name),
                    )
                )

    return metric_candidates, dimension_candidates


# =============================================================================
# Mining from schema
# =============================================================================


def _mine_from_schema(
    schema: dict,
    known_group_by_cols: set[str] | None = None,
) -> tuple[list[MetricCandidate], list[DimensionCandidate]]:
    """Extract dimension candidates from schema descriptions.

    Args:
        schema: Parsed schema descriptions dict.
        known_group_by_cols: Column names (lowercased) seen in GROUP BY clauses
            from training examples. Used to boost confidence.
    """
    metric_candidates: list[MetricCandidate] = []
    dimension_candidates: list[DimensionCandidate] = []

    seen_dimensions: set[str] = set()
    group_cols = known_group_by_cols or set()

    tables = schema.get("tables", [])

    for table in tables:
        if not isinstance(table, dict):
            continue

        table_name = table.get("full_name") or table.get("name", "")
        columns = table.get("columns", [])

        for col in columns:
            if not isinstance(col, dict):
                continue

            col_name = col.get("name", "")
            col_type = col.get("type", "")
            col_desc = col.get("description", "")

            if not col_name:
                continue

            dim_type = _classify_dimension_type(col_name, col_type)

            # Skip entity IDs for dimensions (they're usually not useful for slicing)
            if dim_type == DimensionType.ENTITY:
                continue

            # Build confidence from multiple signals
            confidence = 0.3  # base

            # Type-based boost
            if dim_type == DimensionType.TEMPORAL:
                confidence += 0.15
            elif dim_type == DimensionType.GEOGRAPHIC:
                confidence += 0.1

            # Has a description — someone thought it was important
            if col_desc:
                confidence += 0.1

            # Column type explicitly matches classification
            type_lower = col_type.lower()
            if dim_type == DimensionType.TEMPORAL and any(
                t in type_lower for t in ["date", "timestamp"]
            ):
                confidence += 0.1

            # Appears in GROUP BY in actual queries — strong signal
            col_lower = col_name.lower()
            if col_lower in group_cols:
                confidence += 0.2

            # Cap at 0.95
            confidence = min(round(confidence, 2), 0.95)

            # Skip very low confidence (no signals beyond base)
            if confidence <= 0.3:
                continue

            dim_name = re.sub(r"[^a-z0-9_]", "_", col_name.lower()).strip("_")
            if dim_name in seen_dimensions:
                continue
            seen_dimensions.add(dim_name)

            dimension = Dimension(
                name=dim_name,
                display_name=_extract_display_name(dim_name),
                description=col_desc or f"Column {col_name} from {table_name}",
                type=dim_type,
                column=f"{table_name}.{col_name}" if table_name else col_name,
                tables=[table_name] if table_name else [],
            )

            dimension_candidates.append(
                DimensionCandidate(
                    dimension=dimension,
                    confidence=confidence,
                    source="schema",
                    evidence=[f"{table_name}.{col_name}"],
                    category=_classify_semantic_category(col_name, col_type),
                )
            )

    return metric_candidates, dimension_candidates


# =============================================================================
# Main mining function
# =============================================================================


def _deduplicate_candidates(
    metric_candidates: list[MetricCandidate],
    dimension_candidates: list[DimensionCandidate],
) -> tuple[list[MetricCandidate], list[DimensionCandidate]]:
    """Deduplicate candidates, keeping highest confidence for each name."""
    # Deduplicate metrics
    best_metrics: dict[str, MetricCandidate] = {}
    for c in metric_candidates:
        name = c.metric.name
        if name not in best_metrics or c.confidence > best_metrics[name].confidence:
            best_metrics[name] = c
        else:
            # Merge evidence
            best_metrics[name].evidence.extend(c.evidence)

    # Deduplicate dimensions
    best_dims: dict[str, DimensionCandidate] = {}
    for c in dimension_candidates:
        name = c.dimension.name
        if name not in best_dims or c.confidence > best_dims[name].confidence:
            best_dims[name] = c
        else:
            best_dims[name].evidence.extend(c.evidence)

    return (
        sorted(best_metrics.values(), key=lambda c: c.confidence, reverse=True),
        sorted(best_dims.values(), key=lambda c: c.confidence, reverse=True),
    )


async def mine_metrics_and_dimensions(connection_path: Path) -> dict:
    """Mine the vault for metric and dimension candidates.

    Reads training examples, business rules, and schema descriptions
    to extract metric and dimension candidates using heuristic SQL analysis.

    Args:
        connection_path: Path to the connection directory

    Returns:
        {
            "metric_candidates": [MetricCandidate, ...],
            "dimension_candidates": [DimensionCandidate, ...],
        }
    """
    # Load vault material
    examples = _load_examples(connection_path)
    rules = _load_rules(connection_path)
    schema = _load_schema(connection_path)

    # Mine from each source
    all_metric_candidates: list[MetricCandidate] = []
    all_dimension_candidates: list[DimensionCandidate] = []

    # Collect GROUP BY column names from examples to boost schema confidence
    known_group_by_cols: set[str] = set()

    if examples:
        m, d = _mine_from_examples(examples)
        all_metric_candidates.extend(m)
        all_dimension_candidates.extend(d)
        # Collect dimension names found in GROUP BY clauses
        for dc in d:
            known_group_by_cols.add(dc.dimension.name)
        logger.info(f"Mined {len(m)} metrics, {len(d)} dimensions from {len(examples)} examples")

    if rules:
        m, d = _mine_from_rules(rules)
        all_metric_candidates.extend(m)
        all_dimension_candidates.extend(d)
        logger.info(f"Mined {len(m)} metrics, {len(d)} dimensions from {len(rules)} rules")

    if schema:
        m, d = _mine_from_schema(schema, known_group_by_cols=known_group_by_cols)
        all_metric_candidates.extend(m)
        all_dimension_candidates.extend(d)
        logger.info(f"Mined {len(m)} metrics, {len(d)} dimensions from schema")

    # Deduplicate and rank
    metric_candidates, dimension_candidates = _deduplicate_candidates(
        all_metric_candidates, all_dimension_candidates
    )

    logger.info(
        f"Mining complete: {len(metric_candidates)} metric candidates, "
        f"{len(dimension_candidates)} dimension candidates"
    )

    return {
        "metric_candidates": metric_candidates,
        "dimension_candidates": dimension_candidates,
    }
