"""Canonical vault path constants and helpers.

Single source of truth for file/directory names within a connection vault.
Import from here instead of using magic strings.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# File constants (relative to connection root)
# ---------------------------------------------------------------------------

CONNECTOR_FILE = "connector.yaml"
STATE_FILE = "state.yaml"
PROTOCOL_FILE = "PROTOCOL.md"

# Schema
DESCRIPTIONS_FILE = "schema/descriptions.yaml"

# Domain
DOMAIN_MODEL_FILE = "domain/model.md"

# Instructions
BUSINESS_RULES_FILE = "instructions/business_rules.yaml"
SQL_RULES_FILE = "instructions/sql_rules.md"

# Metrics
METRICS_CATALOG_FILE = "metrics/catalog.yaml"
DIMENSIONS_FILE = "metrics/dimensions.yaml"
METRICS_BINDINGS_FILE = "metrics/bindings.yaml"

# Root-level data files
KNOWLEDGE_GAPS_FILE = "knowledge_gaps.yaml"
FEEDBACK_LOG_FILE = "feedback_log.yaml"

# ---------------------------------------------------------------------------
# Directory constants
# ---------------------------------------------------------------------------

EXAMPLES_DIR = "examples"
LEARNINGS_DIR = "learnings"


# ---------------------------------------------------------------------------
# Path helper functions — return absolute Path given a connection root
# ---------------------------------------------------------------------------


def connector_path(conn_path: Path) -> Path:
    return conn_path / CONNECTOR_FILE


def state_path(conn_path: Path) -> Path:
    return conn_path / STATE_FILE


def protocol_path(conn_path: Path) -> Path:
    return conn_path / PROTOCOL_FILE


def descriptions_path(conn_path: Path) -> Path:
    return conn_path / DESCRIPTIONS_FILE


def domain_model_path(conn_path: Path) -> Path:
    return conn_path / DOMAIN_MODEL_FILE


def business_rules_path(conn_path: Path) -> Path:
    return conn_path / BUSINESS_RULES_FILE


def sql_rules_path(conn_path: Path) -> Path:
    return conn_path / SQL_RULES_FILE


def metrics_catalog_path(conn_path: Path) -> Path:
    return conn_path / METRICS_CATALOG_FILE


def dimensions_path(conn_path: Path) -> Path:
    return conn_path / DIMENSIONS_FILE


def metrics_bindings_path(conn_path: Path) -> Path:
    return conn_path / METRICS_BINDINGS_FILE


def examples_dir(conn_path: Path) -> Path:
    return conn_path / EXAMPLES_DIR


def learnings_dir(conn_path: Path) -> Path:
    return conn_path / LEARNINGS_DIR
