"""Vault file-write services."""

import logging
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

import yaml
from db_mcp_knowledge.vault.paths import (
    BUSINESS_RULES_FILE,
    CONNECTOR_FILE,
    DESCRIPTIONS_FILE,
    DIMENSIONS_FILE,
    DOMAIN_MODEL_FILE,
    EXAMPLES_DIR,
    FEEDBACK_LOG_FILE,
    KNOWLEDGE_GAPS_FILE,
    LEARNINGS_DIR,
    METRICS_BINDINGS_FILE,
    METRICS_CATALOG_FILE,
    PROTOCOL_FILE,
    SQL_RULES_FILE,
)
from db_mcp_models import (
    DimensionsCatalog,
    FeedbackLog,
    KnowledgeGaps,
    MetricBindingsCatalog,
    MetricsCatalog,
    PromptInstructions,
    QueryExample,
    SchemaDescriptions,
)

logger = logging.getLogger(__name__)


def try_git_commit(conn_path: Path, message: str, files: list[str]) -> bool:
    """Commit files via git if .git directory present. Returns True if committed."""
    from db_mcp.services.git import try_git_commit as _try_git_commit

    return _try_git_commit(conn_path, message, files)


def _get_git_for_delete():
    """Lazy import for git rm support in delete operations."""
    from db_mcp_knowledge.git_utils import git

    return git


VAULT_SCHEMA_PATHS: set[str] = {
    DESCRIPTIONS_FILE,
    METRICS_CATALOG_FILE,
    DIMENSIONS_FILE,
    METRICS_BINDINGS_FILE,
    KNOWLEDGE_GAPS_FILE,
    BUSINESS_RULES_FILE,
    FEEDBACK_LOG_FILE,
    "ignore.yaml",
}

VAULT_SCHEMA_GLOBS: set[str] = {
    f"{EXAMPLES_DIR}/*.yaml",
}

VAULT_MARKDOWN_PATHS: set[str] = {
    DOMAIN_MODEL_FILE,
    SQL_RULES_FILE,
    f"{LEARNINGS_DIR}/patterns.md",
    f"{LEARNINGS_DIR}/schema_gotchas.md",
    f"{LEARNINGS_DIR}/trace-analysis-patterns.md",
}

VAULT_MARKDOWN_GLOBS: set[str] = {
    f"{LEARNINGS_DIR}/*.md",
}

CONTEXT_EXTRA_PATHS: set[str] = {
    CONNECTOR_FILE,
    PROTOCOL_FILE,
}

VAULT_SCHEMA_MODELS: dict[str, type] = {
    DESCRIPTIONS_FILE: SchemaDescriptions,
    METRICS_CATALOG_FILE: MetricsCatalog,
    DIMENSIONS_FILE: DimensionsCatalog,
    METRICS_BINDINGS_FILE: MetricBindingsCatalog,
    KNOWLEDGE_GAPS_FILE: KnowledgeGaps,
    BUSINESS_RULES_FILE: PromptInstructions,
    FEEDBACK_LOG_FILE: FeedbackLog,
}

VAULT_SCHEMA_GLOB_MODELS: dict[str, type] = {
    f"{EXAMPLES_DIR}/*.yaml": QueryExample,
}

ARTIFACT_WRITE_TARGETS: dict[str, str] = {
    "schema_descriptions": DESCRIPTIONS_FILE,
    "domain_model": DOMAIN_MODEL_FILE,
    "business_rules": BUSINESS_RULES_FILE,
    "sql_rules": SQL_RULES_FILE,
    "metrics_catalog": METRICS_CATALOG_FILE,
    "metrics_dimensions": DIMENSIONS_FILE,
    "metrics_bindings": METRICS_BINDINGS_FILE,
    "knowledge_gaps": KNOWLEDGE_GAPS_FILE,
    "feedback_log": FEEDBACK_LOG_FILE,
    "ignore": "ignore.yaml",
}

ARTIFACT_APPEND_TARGETS: dict[str, str] = {
    "example": f"{EXAMPLES_DIR}/{{name}}.yaml",
    "learning_note": f"{LEARNINGS_DIR}/{{name}}.md",
}


# ---------------------------------------------------------------------------
# Folder metadata — canonical source of truth for the UI context viewer
# ---------------------------------------------------------------------------

# Importance level shown in the UI for each vault folder
FOLDER_IMPORTANCE: dict[str, str] = {
    "schema": "critical",
    "domain": "critical",
    "examples": "recommended",
    "instructions": "recommended",
    "metrics": "recommended",
    "learnings": "optional",
    "traces": "optional",
}

# Folders that are always shown in the UI even if they don't exist on disk
EXPECTED_FOLDERS: list[str] = [
    "schema",
    "domain",
    "examples",
    "instructions",
    "metrics",
]

# Stock README content shown when a folder exists but has no files yet
STOCK_READMES: dict[str, str] = {
    "schema": """# Schema Descriptions

This directory contains schema descriptions for your database tables and columns.

**Why is this important?**

Schema descriptions are essential for SQL generation. Without them, the AI cannot
understand your database structure and will be unable to generate accurate queries.

## Files

- `descriptions.yaml` - Table and column descriptions used for SQL generation

## How to populate

1. **Recommended**: Run the onboarding process via Claude Desktop or the MCP tools
2. Or manually create `descriptions.yaml` with table/column descriptions

## Format

```yaml
tables:
  - name: users
    full_name: public.users
    description: "User accounts and profiles"
    columns:
      - name: id
        description: "Primary key"
      - name: email
        description: "User email address (unique)"
```

## Getting Started

Ask Claude to help you onboard your database:
> "Let's set up the schema descriptions for my database"
""",
    "domain": """# Domain Model

This directory contains the semantic domain model for your database.

**Why is this important?**

The domain model provides business context that helps the AI understand how your
data relates to real-world concepts, resulting in more accurate and relevant queries.

## Files

- `model.md` - Natural language description of your data domain

## Purpose

The domain model helps the AI understand:
- Business concepts and terminology
- Relationships between entities
- Common query patterns and use cases
- Industry-specific language and metrics

## How to populate

1. **Recommended**: Complete the schema onboarding first, then ask Claude to
   generate the domain model
2. Or manually write a description of your data domain

## Getting Started

After completing schema descriptions, ask Claude:
> "Generate a domain model for my database based on the schema descriptions"
""",
    "examples": """# Query Examples

This directory contains query examples that improve SQL generation accuracy.

**Why is this important?**

Query examples teach the AI your specific query patterns and preferences. The more
examples you provide, the better the AI becomes at generating queries that match your
needs.

## Files

Each example is stored as a separate YAML file with natural language and SQL mapping.

## Format

```yaml
natural_language: "Show me all active users"
sql: "SELECT * FROM users WHERE status = 'active'"
tags: ["users", "status"]
notes: "Filter by status column"
```

## How to add examples

1. **Easiest**: After a successful query, provide feedback to save it as an example
2. Or manually create YAML files in this directory

## Getting Started

Start using the database with natural language queries. After each successful query,
you can save it as an example to improve future results.
""",
    "instructions": """# Business Rules & Instructions

This directory contains business rules and special instructions for SQL generation.

**Why is this important?**

Business rules ensure that generated queries follow your organization's conventions,
data access policies, and best practices. They provide guardrails and context that
improve query quality.

## Files

- `business_rules.yaml` - List of rules and instructions

## Format

```yaml
rules:
  - "Always use UTC timestamps"
  - "Filter deleted records with is_deleted = false"
  - "Use INNER JOIN for customer tables"
  - "Limit results to 1000 rows by default"
```

## Examples of Business Rules

- Data access restrictions (e.g., "Only query data from the last 90 days")
- Naming conventions (e.g., "Date columns end with _at or _date")
- Performance guidelines (e.g., "Always include partition key in WHERE clause")
- Business logic (e.g., "Active users are those with last_login in past 30 days")

## Getting Started

Think about the rules and conventions your team follows when writing queries,
and document them here.
""",
    "metrics": """# Business Metrics

This directory contains standardized metric definitions for your organization.

**Why is this important?**

Metric definitions ensure consistent calculation of KPIs across all queries. Instead
of re-defining "Monthly Active Users" each time, you define it once and reference it
consistently.

## Files

- `catalog.yaml` - Metric definitions catalog

## Format

```yaml
metrics:
  - name: monthly_active_users
    display_name: "Monthly Active Users"
    description: "Users who logged in at least once in the past 30 days"
    sql: "COUNT(DISTINCT user_id) FILTER (WHERE last_login >= CURRENT_DATE - 30)"
    tables: ["users"]
    tags: ["engagement", "core-kpi"]
```

## Common Metric Types

- **Engagement**: DAU, WAU, MAU, session duration
- **Revenue**: MRR, ARR, ARPU, LTV
- **Growth**: Signups, activations, churn rate
- **Operations**: Response time, error rate, uptime

## Getting Started

Start by defining your organization's most important KPIs - the metrics that appear
in executive dashboards and reports.
""",
    "learnings": """# Learnings

This directory contains patterns and insights learned from your query history.

**Why is this important?**

Learnings capture institutional knowledge about your data - schema quirks, common
pitfalls, and best practices discovered through usage. This helps the AI avoid
known issues and follow proven patterns.

## Files

- `patterns.md` - Common query patterns and techniques
- `schema_gotchas.md` - Schema-specific quirks and workarounds

## What to document

- **Schema quirks**: "The `status` column uses 0/1 instead of boolean"
- **Naming conventions**: "Date columns use `_at` suffix, not `_date`"
- **Performance tips**: "Always filter by `tenant_id` first for faster queries"
- **Data quality issues**: "Some `email` values are null for legacy accounts"
- **Business logic**: "Revenue calculations should exclude refunded orders"

## Getting Started

As you work with your database, document any insights or gotchas you discover.
This knowledge helps the AI generate better queries over time.
""",
}


def _normalize_vault_path(path: str) -> str:
    return PurePosixPath(path).as_posix().lstrip("/")


def _normalize_artifact_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-_")
    return normalized


def _is_allowed_write_path(path: str) -> bool:
    if path in VAULT_SCHEMA_PATHS or path in VAULT_MARKDOWN_PATHS:
        return True
    return any(fnmatch(path, pattern) for pattern in VAULT_SCHEMA_GLOBS | VAULT_MARKDOWN_GLOBS)


def _is_allowed_context_path(path: str) -> bool:
    return path in CONTEXT_EXTRA_PATHS or _is_allowed_write_path(path)


def _validate_sql_fields(model_instance) -> None:
    """Validate fields annotated with ``is_sql`` metadata via sqlglot."""
    import sqlglot

    for name, field_info in type(model_instance).model_fields.items():
        extra = field_info.json_schema_extra or {}
        if not extra.get("is_sql"):
            continue
        value = getattr(model_instance, name, None)
        if not value or not isinstance(value, str):
            continue
        try:
            sqlglot.parse(value)
        except sqlglot.errors.ErrorLevel:
            raise
        except Exception as exc:
            raise ValueError(f"Field '{name}' contains invalid SQL: {exc}") from exc


def _validate_content(path: str, content: str) -> None:
    model_class = VAULT_SCHEMA_MODELS.get(path)
    if model_class is None:
        for pattern, glob_model in VAULT_SCHEMA_GLOB_MODELS.items():
            if fnmatch(path, pattern):
                model_class = glob_model
                break
    if model_class is None:
        return
    data = yaml.safe_load(content)
    instance = model_class.model_validate(data)
    _validate_sql_fields(instance)


def _atomic_write_text(target: Path, content: str) -> None:
    temp_target = target.with_suffix(f"{target.suffix}.tmp")
    try:
        temp_target.write_text(content, encoding="utf-8")
        os.replace(str(temp_target), str(target))
    finally:
        if temp_target.exists():
            temp_target.unlink()


def vault_write(connection_path: Path, path: str, content: str) -> dict:
    """Write a whitelisted vault file."""
    normalized_path = _normalize_vault_path(path)
    if not _is_allowed_write_path(normalized_path):
        return {
            "saved": False,
            "file_path": None,
            "error": f"Vault path '{normalized_path}' is not allowed for vault_write.",
        }
    try:
        _validate_content(normalized_path, content)
    except Exception as exc:
        return {
            "saved": False,
            "file_path": None,
            "error": str(exc),
        }

    target = connection_path / normalized_path
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, content)
    return {
        "saved": True,
        "file_path": str(target),
        "error": None,
    }


def vault_append(connection_path: Path, path: str, content: str) -> dict:
    """Append or create an allowed vault file."""
    normalized_path = _normalize_vault_path(path)
    is_schema_glob = any(fnmatch(normalized_path, pattern) for pattern in VAULT_SCHEMA_GLOBS)
    is_markdown_glob = any(fnmatch(normalized_path, pattern) for pattern in VAULT_MARKDOWN_GLOBS)
    if not is_schema_glob and not is_markdown_glob:
        return {
            "saved": False,
            "file_path": None,
            "error": f"Vault path '{normalized_path}' is not allowed for vault_append.",
        }

    try:
        _validate_content(normalized_path, content)
    except Exception as exc:
        return {
            "saved": False,
            "file_path": None,
            "error": str(exc),
        }

    target = connection_path / normalized_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if is_schema_glob and target.exists():
        return {
            "saved": False,
            "file_path": None,
            "error": f"Vault path '{normalized_path}' already exists.",
        }
    if is_markdown_glob:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        _atomic_write_text(target, existing + content)
    else:
        _atomic_write_text(target, content)
    return {
        "saved": True,
        "file_path": str(target),
        "error": None,
    }


def save_artifact(
    connection_path: Path,
    artifact_type: str,
    content: str,
    name: str | None = None,
) -> dict:
    """Persist a typed artifact into the connection vault."""
    normalized_type = artifact_type.strip().lower()

    if normalized_type in ARTIFACT_WRITE_TARGETS:
        result = vault_write(
            connection_path=connection_path,
            path=ARTIFACT_WRITE_TARGETS[normalized_type],
            content=content,
        )
    elif normalized_type in ARTIFACT_APPEND_TARGETS:
        if not name:
            return {
                "saved": False,
                "artifact_type": normalized_type,
                "file_path": None,
                "error": f"Artifact type '{normalized_type}' requires a name.",
            }
        normalized_name = _normalize_artifact_name(name)
        if not normalized_name:
            return {
                "saved": False,
                "artifact_type": normalized_type,
                "file_path": None,
                "error": "Artifact name is invalid.",
            }
        result = vault_append(
            connection_path=connection_path,
            path=ARTIFACT_APPEND_TARGETS[normalized_type].format(name=normalized_name),
            content=content,
        )
    else:
        return {
            "saved": False,
            "artifact_type": normalized_type,
            "file_path": None,
            "error": f"Unsupported artifact type '{normalized_type}'.",
        }

    return {
        **result,
        "artifact_type": normalized_type,
    }


def read_context_file(
    connection_path: Path,
    path: str,
    stock_readmes: dict[str, str] | None = None,
) -> dict:
    """Read an allowed vault/context file.

    Falls back to ``STOCK_READMES`` when the file/folder doesn't exist and no
    explicit *stock_readmes* override is supplied.
    """
    if stock_readmes is None:
        stock_readmes = STOCK_READMES
    if ".." in path or path.startswith("/"):
        return {"success": False, "error": "Invalid path"}

    file_path = connection_path / path

    if file_path.is_dir():
        folder_name = path.split("/")[0] if "/" in path else path
        if stock_readmes and folder_name in stock_readmes:
            return {
                "success": True,
                "content": stock_readmes[folder_name],
                "isStockReadme": True,
                "error": None,
            }
        return {"success": False, "error": "Folder has no setup guide"}

    if not file_path.exists():
        parts = path.split("/")
        if stock_readmes and len(parts) == 1 and parts[0] in stock_readmes:
            return {
                "success": True,
                "content": stock_readmes[parts[0]],
                "isStockReadme": True,
                "error": None,
            }
        return {"success": False, "error": f"File not found: {path}"}

    if file_path.suffix.lower() not in {".yaml", ".yml", ".md"}:
        return {"success": False, "error": "File type not allowed"}

    try:
        return {
            "success": True,
            "content": file_path.read_text(encoding="utf-8"),
            "error": None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_context_file(connection_path: Path, path: str, content: str) -> dict:
    """Write an allowed context file under a connection directory."""
    normalized_path = _normalize_vault_path(path)
    if ".." in path or path.startswith("/"):
        return {"success": False, "error": "Invalid path"}

    if not _is_allowed_context_path(normalized_path):
        return {
            "success": False,
            "error": f"Vault path '{normalized_path}' is not allowed for context writes.",
        }

    if not connection_path.exists():
        return {"success": False, "error": f"Connection '{connection_path.name}' not found"}

    try:
        _validate_content(normalized_path, content)
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    file_path = connection_path / normalized_path
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(file_path, content)
        git_committed = try_git_commit(
            connection_path, f"Update {normalized_path}", [normalized_path]
        )
        return {"success": True, "gitCommit": git_committed, "error": None}
    except Exception as e:
        return {"success": False, "gitCommit": False, "error": str(e)}


def create_context_file(connection_path: Path, path: str, content: str = "") -> dict:
    """Create a new allowed context file under a connection directory."""
    normalized_path = _normalize_vault_path(path)
    if ".." in path or path.startswith("/"):
        return {"success": False, "error": "Invalid path"}

    if not _is_allowed_context_path(normalized_path):
        return {
            "success": False,
            "error": f"Vault path '{normalized_path}' is not allowed for context writes.",
        }

    try:
        _validate_content(normalized_path, content)
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    connection_path.mkdir(parents=True, exist_ok=True)

    file_path = connection_path / normalized_path
    if file_path.exists():
        return {
            "success": False,
            "gitCommit": False,
            "error": f"File already exists: {normalized_path}",
        }

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(file_path, content)
        git_committed = try_git_commit(
            connection_path, f"Create {normalized_path}", [normalized_path]
        )
        return {"success": True, "gitCommit": git_committed, "error": None}
    except Exception as e:
        return {"success": False, "gitCommit": False, "error": str(e)}


def delete_context_file(connection_path: Path, path: str) -> dict:
    """Delete a context file.

    Uses ``git rm`` + commit when git is enabled, otherwise moves the file
    to the connection ``.trash`` directory.
    """
    if ".." in path or path.startswith("/"):
        return {"success": False, "error": "Invalid path"}

    if not connection_path.exists():
        return {"success": False, "error": f"Connection '{connection_path.name}' not found"}

    file_path = connection_path / path
    if not file_path.exists():
        return {"success": False, "error": f"File not found: {path}"}

    try:
        if (connection_path / ".git").exists():
            git = _get_git_for_delete()
            git.rm(connection_path, path)
            git.commit(connection_path, f"Delete {path}")
            return {"success": True, "gitCommit": True, "trashedTo": None}

        trash_dir = connection_path / ".trash"
        trash_dir.mkdir(exist_ok=True)

        trash_path = trash_dir / file_path.name
        counter = 1
        while trash_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            trash_path = trash_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        shutil.move(str(file_path), str(trash_path))
        return {
            "success": True,
            "gitCommit": False,
            "trashedTo": f".trash/{trash_path.name}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_business_rule(connection_path: Path, connection_name: str, rule: str) -> dict:
    """Append a business rule to instructions/business_rules.yaml."""
    if not connection_path.exists():
        return {
            "success": False,
            "duplicate": False,
            "error": f"Connection '{connection_name}' not found",
        }

    rules_path = connection_path / BUSINESS_RULES_FILE

    try:
        if rules_path.exists():
            with open(rules_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            rules_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0.0",
                "provider_id": connection_name,
                "rules": [],
            }

        rules = data.get("rules", [])
        if not isinstance(rules, list):
            rules = []

        if rule in rules:
            return {"success": True, "duplicate": True, "error": None}

        rules.append(rule)
        data["rules"] = rules

        with open(rules_path, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        git_committed = try_git_commit(
            connection_path, "Add business rule", [BUSINESS_RULES_FILE]
        )
        return {"success": True, "duplicate": False, "gitCommit": git_committed, "error": None}
    except Exception as e:
        return {"success": False, "duplicate": False, "gitCommit": False, "error": str(e)}


def list_context_tree(
    connections_dir: Path,
    active_connection: str | None,
    is_git_enabled,
    expected_folders: tuple[str, ...] | list[str] | None = None,
    folder_importance: dict[str, str] | None = None,
    stock_readmes: dict[str, str] | None = None,
) -> dict:
    """List the context tree for all connections.

    *expected_folders*, *folder_importance*, and *stock_readmes* all fall back
    to the module-level constants when not supplied.
    """
    if expected_folders is None:
        expected_folders = EXPECTED_FOLDERS
    if folder_importance is None:
        folder_importance = FOLDER_IMPORTANCE
    if stock_readmes is None:
        stock_readmes = STOCK_READMES
    """List the context tree for all connections."""
    allowed_extensions = {".yaml", ".yml", ".md"}
    hidden_prefixes = (".", "_")
    from db_mcp_knowledge.vault.paths import STATE_FILE

    skip_files = {STATE_FILE}

    connections = []
    if connections_dir.exists():
        for conn_path in sorted(connections_dir.iterdir()):
            if not conn_path.is_dir():
                continue

            name = conn_path.name
            git_enabled = is_git_enabled(conn_path)

            folders = []
            root_files = []

            for item_path in sorted(conn_path.iterdir()):
                item_name = item_path.name
                if item_name.startswith(hidden_prefixes):
                    continue
                if item_name in skip_files:
                    continue

                if item_path.is_dir():
                    files = []
                    for file_path in sorted(item_path.iterdir()):
                        if not file_path.is_file():
                            continue
                        if file_path.name.startswith(hidden_prefixes):
                            continue
                        if file_path.suffix.lower() not in allowed_extensions:
                            continue

                        files.append(
                            {
                                "name": file_path.name,
                                "path": f"{item_name}/{file_path.name}",
                                "size": file_path.stat().st_size,
                            }
                        )

                    has_nested_files = any(
                        nested.is_file() and not nested.name.startswith(hidden_prefixes)
                        for nested in item_path.rglob("*")
                    )

                    folders.append(
                        {
                            "name": item_name,
                            "path": item_name,
                            "files": files,
                            "isEmpty": len(files) == 0 and not has_nested_files,
                            "importance": folder_importance.get(item_name),
                            "hasReadme": item_name in stock_readmes,
                        }
                    )

                elif item_path.is_file():
                    if item_path.suffix.lower() not in allowed_extensions:
                        continue

                    root_files.append(
                        {
                            "name": item_name,
                            "path": item_name,
                            "size": item_path.stat().st_size,
                        }
                    )

            existing_folder_names = {f["name"] for f in folders}
            for expected_folder in expected_folders:
                if expected_folder not in existing_folder_names:
                    folder_path = conn_path / expected_folder
                    folder_path.mkdir(exist_ok=True)
                    folders.append(
                        {
                            "name": expected_folder,
                            "path": expected_folder,
                            "files": [],
                            "isEmpty": True,
                            "importance": folder_importance.get(expected_folder),
                            "hasReadme": expected_folder in stock_readmes,
                        }
                    )

            folders.sort(key=lambda f: f["name"])
            connections.append(
                {
                    "name": name,
                    "isActive": name == active_connection,
                    "gitEnabled": git_enabled,
                    "folders": folders,
                    "rootFiles": root_files,
                }
            )

    return {"connections": connections}


def get_context_usage(connection_path: Path, days: int = 7) -> dict:
    """Aggregate context file usage from trace files."""
    import re as _re
    import time
    import urllib.parse

    from db_mcp.traces_reader import list_trace_dates, read_traces_from_jsonl

    cutoff_time = time.time() - (days * 86400)
    traces_dir = connection_path / "traces"
    user_ids = []
    if traces_dir.exists():
        user_ids = [
            d.name for d in traces_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]
    if not user_ids:
        user_ids = ["default"]

    file_counts = defaultdict(int)
    file_last_used: dict[str, float] = {}
    ctx_dirs = (
        "schema",
        "examples",
        "instructions",
        "domain",
        "data",
        "learnings",
        "metrics",
    )
    root_files = ("PROTOCOL.md", "connector.yaml", "knowledge_gaps.yaml")

    def _normalize_context_path(raw_path: str | None) -> str | None:
        if not raw_path or not isinstance(raw_path, str):
            return None

        cleaned = urllib.parse.unquote(raw_path.replace("file://", "")).strip().strip("\"'")
        path_obj = Path(cleaned)

        if path_obj.is_absolute() and connection_path not in path_obj.parents:
            return None

        if path_obj.name in root_files:
            return path_obj.name

        parts = path_obj.parts
        for idx, part in enumerate(parts):
            if part in ctx_dirs and idx + 1 < len(parts):
                return "/".join(parts[idx:])

        return None

    for user_id in user_ids:
        available_dates = list_trace_dates(connection_path, user_id)

        for date_str in available_dates:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if date_obj.timestamp() < cutoff_time:
                    continue
            except ValueError:
                continue

            trace_file = connection_path / "traces" / user_id / f"{date_str}.jsonl"
            if not trace_file.exists():
                continue

            traces = read_traces_from_jsonl(trace_file, limit=None)

            for trace in traces:
                for span in trace.get("spans", []):
                    attrs = span.get("attributes", {})
                    span_timestamp = span.get("start_time", 0)

                    def _track(file_key: str) -> None:
                        file_counts[file_key] += 1
                        prev = file_last_used.get(file_key, 0)
                        file_last_used[file_key] = max(prev, span_timestamp)

                    tool_name = attrs.get("tool.name")
                    command = attrs.get("command")
                    if tool_name == "shell" and command:
                        for match in _re.finditer(
                            r"(?:^|[\s/])(" + "|".join(ctx_dirs) + r")/([^\s;|>&]+)",
                            command,
                        ):
                            _track(f"{match.group(1)}/{match.group(2)}")
                        for root_file in _re.findall(
                            r"(?:^|[\s/])("
                            + "|".join(_re.escape(name) for name in root_files)
                            + r")(?=$|[\s;|>&])",
                            command,
                        ):
                            _track(root_file)

                    if tool_name == "protocol_tool":
                        _track("PROTOCOL.md")

                    files_used = attrs.get("knowledge.files_used")
                    if files_used:
                        for file_path in files_used:
                            normalized = _normalize_context_path(file_path)
                            if normalized:
                                _track(normalized)

                    for attr_name in ("path", "file_path", "resource.uri"):
                        normalized = _normalize_context_path(attrs.get(attr_name))
                        if normalized:
                            _track(normalized)

    folder_counts = defaultdict(int)
    folder_last_used: dict[str, float] = {}

    for file_path, count in file_counts.items():
        if "/" in file_path:
            folder = file_path.split("/")[0]
            folder_counts[folder] += count
            prev = folder_last_used.get(folder, 0)
            last = file_last_used.get(file_path, 0)
            folder_last_used[folder] = max(prev, last)

    return {
        "files": {
            path: {"count": count, "lastUsed": int(file_last_used.get(path, 0))}
            for path, count in file_counts.items()
        },
        "folders": {
            path: {"count": count, "lastUsed": int(folder_last_used.get(path, 0))}
            for path, count in folder_counts.items()
        },
    }
