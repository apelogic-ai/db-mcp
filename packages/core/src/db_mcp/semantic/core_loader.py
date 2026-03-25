"""Load approved semantic artifacts for the current connection.

The full V1 design calls for an org/domain semantic core above connections.
The first slice intentionally bootstraps from the connection-local approved
metrics and dimensions that already exist in the vault.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from db_mcp_models import Dimension, Metric, MetricBinding, SemanticPolicy

from db_mcp.business_rules import compile_semantic_policy
from db_mcp.config import get_settings
from db_mcp.metrics.store import load_dimensions, load_metric_bindings, load_metrics


@dataclass(slots=True)
class ConnectionSemanticCore:
    """Approved semantic artifacts available for one connection."""

    provider_id: str
    metrics: list[Metric]
    dimensions: list[Dimension]
    metric_bindings: dict[str, MetricBinding]
    policy: SemanticPolicy = field(
        default_factory=lambda: SemanticPolicy(provider_id="unknown")
    )

    def get_metric(self, name: str) -> Metric | None:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        return None

    def get_metric_binding(self, metric_name: str) -> MetricBinding | None:
        return self.metric_bindings.get(metric_name)


def load_connection_semantic_core(
    provider_id: str,
    *,
    connection_path: Path | str | None = None,
) -> ConnectionSemanticCore:
    """Load approved metrics and dimensions for serving.

    The serving path ignores candidate items by default.
    """
    metrics_catalog = load_metrics(provider_id, connection_path=connection_path)
    dimensions_catalog = load_dimensions(provider_id, connection_path=connection_path)
    bindings_catalog = load_metric_bindings(provider_id, connection_path=connection_path)
    if connection_path is not None:
        connection_root = Path(connection_path)
    else:
        settings = get_settings()
        if settings.connections_dir:
            connection_root = Path(settings.connections_dir) / provider_id
        elif settings.connection_path:
            connection_root = Path(settings.connection_path)
        else:
            connection_root = Path.home() / ".db-mcp" / "connections" / provider_id
    policy_payload = None
    rules_path = connection_root / "instructions" / "business_rules.yaml"
    if rules_path.exists():
        try:
            policy_payload = yaml.safe_load(rules_path.read_text())
        except Exception:
            policy_payload = None

    return ConnectionSemanticCore(
        provider_id=provider_id,
        metrics=metrics_catalog.approved(),
        dimensions=dimensions_catalog.approved(),
        metric_bindings=bindings_catalog.bindings,
        policy=compile_semantic_policy(provider_id, policy_payload),
    )
