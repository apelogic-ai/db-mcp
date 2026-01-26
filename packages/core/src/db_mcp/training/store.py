"""Training data persistence - examples and feedback.

Examples are stored as individual YAML files in the examples/ folder.
This makes git diffs cleaner and allows per-example management.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from db_mcp_models import (
    FeedbackLog,
    FeedbackType,
    PromptInstructions,
    QueryExample,
    QueryExamples,
    QueryFeedback,
)

from db_mcp.onboarding.state import get_provider_dir


def get_examples_dir(provider_id: str) -> Path:
    """Get path to examples directory."""
    return get_provider_dir(provider_id) / "examples"


def get_feedback_file_path(provider_id: str) -> Path:
    """Get path to feedback log file."""
    return get_provider_dir(provider_id) / "feedback_log.yaml"


def get_instructions_dir(provider_id: str) -> Path:
    """Get path to instructions directory."""
    return get_provider_dir(provider_id) / "instructions"


def get_instructions_file_path(provider_id: str) -> Path:
    """Get path to business rules file."""
    return get_instructions_dir(provider_id) / "business_rules.yaml"


# =============================================================================
# Query Examples (Folder-based storage)
# =============================================================================


def _example_to_file_format(example: QueryExample) -> dict:
    """Convert QueryExample to file format for saving."""
    return {
        "id": example.id,
        "intent": example.natural_language,
        "sql": example.sql,
        "tables": example.tables_used,
        "keywords": example.tags,
        "notes": example.notes,
        "validated": True,
        "created_at": example.created_at.isoformat() if example.created_at else None,
        "created_by": example.created_by,
    }


def _file_format_to_example(data: dict, file_id: str) -> QueryExample:
    """Convert file format to QueryExample."""
    # Handle created_at parsing
    created_at = None
    if data.get("created_at"):
        try:
            created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(UTC)
    elif data.get("created"):
        # Legacy field name
        try:
            created_at = datetime.fromisoformat(data["created"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(UTC)
    else:
        created_at = datetime.now(UTC)

    return QueryExample(
        id=data.get("id", file_id),
        natural_language=data.get("intent", data.get("natural_language", "")),
        sql=data.get("sql", ""),
        tables_used=data.get("tables", data.get("tables_used", [])),
        tags=data.get("keywords", data.get("tags", [])),
        notes=data.get("notes"),
        created_at=created_at,
        created_by=data.get("created_by"),
    )


def load_examples(provider_id: str) -> QueryExamples:
    """Load query examples from examples/ folder.

    Note: Legacy query_examples.yaml migration is handled by the migrations
    system (see db_mcp.migrations). This function only reads from examples/.

    Args:
        provider_id: Provider identifier

    Returns:
        QueryExamples collection
    """
    examples_dir = get_examples_dir(provider_id)
    examples_list: list[QueryExample] = []

    # Load from examples/ folder
    if examples_dir.exists():
        for file_path in sorted(examples_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in (".yaml", ".yml"):
                continue
            if file_path.name.startswith("."):
                continue

            try:
                with open(file_path) as f:
                    data = yaml.safe_load(f)
                if data:
                    file_id = file_path.stem
                    example = _file_format_to_example(data, file_id)
                    examples_list.append(example)
            except Exception:
                # Skip invalid files
                continue

    return QueryExamples(provider_id=provider_id, examples=examples_list)


def save_example(provider_id: str, example: QueryExample) -> dict:
    """Save a single example to its own file.

    Args:
        provider_id: Provider identifier
        example: QueryExample to save

    Returns:
        Dict with save status
    """
    try:
        examples_dir = get_examples_dir(provider_id)
        examples_dir.mkdir(parents=True, exist_ok=True)

        file_data = _example_to_file_format(example)
        file_path = examples_dir / f"{example.id}.yaml"

        with open(file_path, "w") as f:
            yaml.dump(
                file_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(file_path), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


def delete_example(provider_id: str, example_id: str) -> dict:
    """Delete an example file.

    Args:
        provider_id: Provider identifier
        example_id: Example ID to delete

    Returns:
        Dict with delete status
    """
    try:
        examples_dir = get_examples_dir(provider_id)
        file_path = examples_dir / f"{example_id}.yaml"

        if file_path.exists():
            file_path.unlink()
            return {"deleted": True, "file_path": str(file_path), "error": None}
        else:
            return {"deleted": False, "error": f"Example {example_id} not found"}
    except Exception as e:
        return {"deleted": False, "error": str(e)}


def add_example(
    provider_id: str,
    natural_language: str,
    sql: str,
    tables_used: list[str] | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Add a new query example.

    Args:
        provider_id: Provider identifier
        natural_language: Natural language query
        sql: Correct SQL
        tables_used: Tables referenced in the query
        tags: Tags for categorization
        notes: Additional notes

    Returns:
        Dict with example ID and status
    """
    example = QueryExample(
        id=str(uuid.uuid4())[:8],
        natural_language=natural_language,
        sql=sql,
        tables_used=tables_used or [],
        tags=tags or [],
        notes=notes,
        created_at=datetime.now(UTC),
    )

    result = save_example(provider_id, example)

    if result["saved"]:
        # Count total examples
        examples = load_examples(provider_id)
        return {
            "added": True,
            "example_id": example.id,
            "total_examples": examples.count(),
            "file_path": result["file_path"],
        }
    else:
        return {"added": False, "error": result["error"]}


# Legacy function for backward compatibility
def save_examples(examples: QueryExamples) -> dict:
    """Save all examples (backward compatibility).

    Note: This now saves each example as individual files.
    """
    try:
        for example in examples.examples:
            result = save_example(examples.provider_id, example)
            if not result["saved"]:
                return result

        examples_dir = get_examples_dir(examples.provider_id)
        return {"saved": True, "file_path": str(examples_dir), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


# =============================================================================
# Feedback Log
# =============================================================================


def load_feedback(provider_id: str) -> FeedbackLog:
    """Load feedback log from YAML file.

    Args:
        provider_id: Provider identifier

    Returns:
        FeedbackLog (empty if file doesn't exist)
    """
    feedback_file = get_feedback_file_path(provider_id)

    if not feedback_file.exists():
        return FeedbackLog(provider_id=provider_id)

    try:
        with open(feedback_file) as f:
            data = yaml.safe_load(f)
        return FeedbackLog.model_validate(data)
    except Exception:
        return FeedbackLog(provider_id=provider_id)


def save_feedback(feedback_log: FeedbackLog) -> dict:
    """Save feedback log to YAML file.

    Args:
        feedback_log: FeedbackLog to save

    Returns:
        Dict with save status
    """
    try:
        provider_dir = get_provider_dir(feedback_log.provider_id)
        provider_dir.mkdir(parents=True, exist_ok=True)

        feedback_dict = feedback_log.model_dump(mode="json")

        feedback_file = get_feedback_file_path(feedback_log.provider_id)
        with open(feedback_file, "w") as f:
            yaml.dump(
                feedback_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(feedback_file), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


def add_feedback(
    provider_id: str,
    natural_language: str,
    generated_sql: str,
    feedback_type: FeedbackType,
    corrected_sql: str | None = None,
    feedback_text: str | None = None,
    tables_involved: list[str] | None = None,
) -> dict:
    """Add a new feedback record.

    Args:
        provider_id: Provider identifier
        natural_language: Original natural language query
        generated_sql: SQL that was generated
        feedback_type: Type of feedback
        corrected_sql: User-provided correction (if any)
        feedback_text: User explanation
        tables_involved: Tables referenced

    Returns:
        Dict with feedback ID and status
    """
    feedback_log = load_feedback(provider_id)

    fb = QueryFeedback(
        id=str(uuid.uuid4())[:8],
        natural_language=natural_language,
        generated_sql=generated_sql,
        feedback_type=feedback_type,
        corrected_sql=corrected_sql,
        feedback_text=feedback_text,
        tables_involved=tables_involved or [],
        created_at=datetime.now(UTC),
    )

    feedback_log.add_feedback(fb)
    result = save_feedback(feedback_log)

    if result["saved"]:
        return {
            "added": True,
            "feedback_id": fb.id,
            "feedback_type": feedback_type.value,
            "total_feedback": len(feedback_log.feedback),
        }
    else:
        return {"added": False, "error": result["error"]}


# =============================================================================
# Prompt Instructions
# =============================================================================


def load_instructions(provider_id: str) -> PromptInstructions:
    """Load prompt instructions from YAML file.

    Args:
        provider_id: Provider identifier

    Returns:
        PromptInstructions (empty if file doesn't exist)
    """
    instructions_file = get_instructions_file_path(provider_id)

    if not instructions_file.exists():
        return PromptInstructions(provider_id=provider_id)

    try:
        with open(instructions_file) as f:
            data = yaml.safe_load(f)
        return PromptInstructions.model_validate(data)
    except Exception:
        return PromptInstructions(provider_id=provider_id)


def save_instructions(instructions: PromptInstructions) -> dict:
    """Save prompt instructions to YAML file.

    Args:
        instructions: PromptInstructions to save

    Returns:
        Dict with save status
    """
    try:
        instructions_dir = get_instructions_dir(instructions.provider_id)
        instructions_dir.mkdir(parents=True, exist_ok=True)

        instructions_dict = instructions.model_dump(mode="json")

        instructions_file = get_instructions_file_path(instructions.provider_id)
        with open(instructions_file, "w") as f:
            yaml.dump(
                instructions_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(instructions_file), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


def add_rule(provider_id: str, rule: str) -> dict:
    """Add a business rule to prompt instructions.

    Args:
        provider_id: Provider identifier
        rule: Business rule text

    Returns:
        Dict with status
    """
    instructions = load_instructions(provider_id)
    instructions.add_rule(rule)
    result = save_instructions(instructions)

    if result["saved"]:
        return {
            "added": True,
            "total_rules": len(instructions.rules),
            "file_path": result["file_path"],
        }
    else:
        return {"added": False, "error": result["error"]}


# =============================================================================
# Bulk Import Functions
# =============================================================================


def import_instructions_from_legacy(provider_id: str, yaml_content: str) -> dict:
    """Import instructions from legacy format YAML.

    Legacy format:
        version: 1.0.0
        profiles:
            wh_v2:
                - "rule 1"
                - "rule 2"

    Args:
        provider_id: Provider identifier
        yaml_content: YAML string in legacy format

    Returns:
        Dict with import status
    """
    try:
        data = yaml.safe_load(yaml_content)

        if not data or "profiles" not in data:
            return {"imported": False, "error": "Invalid format: missing 'profiles' key"}

        profiles = data.get("profiles", {})
        all_rules = []

        # Collect rules from all profiles
        for profile_name, rules in profiles.items():
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, str) and rule.strip():
                        all_rules.append(rule.strip())

        if not all_rules:
            return {"imported": False, "error": "No rules found in profiles"}

        # Load existing or create new
        instructions = load_instructions(provider_id)

        # Add rules (avoiding duplicates)
        added_count = 0
        for rule in all_rules:
            if rule not in instructions.rules:
                instructions.add_rule(rule)
                added_count += 1

        result = save_instructions(instructions)

        if result["saved"]:
            return {
                "imported": True,
                "rules_found": len(all_rules),
                "rules_added": added_count,
                "rules_skipped": len(all_rules) - added_count,
                "total_rules": len(instructions.rules),
                "file_path": result["file_path"],
            }
        else:
            return {"imported": False, "error": result["error"]}

    except yaml.YAMLError as e:
        return {"imported": False, "error": f"YAML parse error: {e}"}
    except Exception as e:
        return {"imported": False, "error": str(e)}


def import_examples_from_legacy(provider_id: str, yaml_content: str) -> dict:
    """Import examples from legacy format YAML.

    Legacy format:
        version: 1.0.0
        profiles:
            wh_v2:
                examples:
                    - request: "natural language"
                      response: |
                          SELECT ...
                      db: wh_v2

    Args:
        provider_id: Provider identifier
        yaml_content: YAML string in legacy format

    Returns:
        Dict with import status
    """
    try:
        data = yaml.safe_load(yaml_content)

        if not data or "profiles" not in data:
            return {"imported": False, "error": "Invalid format: missing 'profiles' key"}

        profiles = data.get("profiles", {})
        all_examples = []

        # Collect examples from all profiles
        for profile_name, profile_data in profiles.items():
            if isinstance(profile_data, dict):
                examples = profile_data.get("examples", [])
            elif isinstance(profile_data, list):
                # Some formats have examples directly as list
                examples = profile_data
            else:
                continue

            for ex in examples:
                if isinstance(ex, dict):
                    request = ex.get("request", "").strip()
                    response = ex.get("response", "").strip()
                    if request and response:
                        all_examples.append(
                            {
                                "natural_language": request,
                                "sql": response,
                                "profile": profile_name,
                                "db": ex.get("db", profile_name),
                            }
                        )

        if not all_examples:
            return {"imported": False, "error": "No examples found in profiles"}

        # Load existing examples to check for duplicates
        examples_store = load_examples(provider_id)
        existing_nl = {e.natural_language for e in examples_store.examples}

        added_count = 0
        for ex in all_examples:
            if ex["natural_language"] not in existing_nl:
                example = QueryExample(
                    id=str(uuid.uuid4())[:8],
                    natural_language=ex["natural_language"],
                    sql=ex["sql"],
                    tables_used=[],
                    tags=[ex.get("db", ""), ex.get("profile", "")],
                    notes=f"Imported from legacy format (profile: {ex.get('profile', 'unknown')})",
                    created_at=datetime.now(UTC),
                )
                save_example(provider_id, example)
                existing_nl.add(ex["natural_language"])
                added_count += 1

        # Reload to get accurate count
        examples_store = load_examples(provider_id)

        return {
            "imported": True,
            "examples_found": len(all_examples),
            "examples_added": added_count,
            "examples_skipped": len(all_examples) - added_count,
            "total_examples": examples_store.count(),
            "file_path": str(get_examples_dir(provider_id)),
        }

    except yaml.YAMLError as e:
        return {"imported": False, "error": f"YAML parse error: {e}"}
    except Exception as e:
        return {"imported": False, "error": str(e)}
