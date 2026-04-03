"""Shell tool for knowledge vault access.

Provides a sandboxed bash interface for Claude to read, search, and append
knowledge in the vault directory. Commands are strictly validated against
an allowlist to prevent security issues.
"""

import asyncio
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Re-export from the canonical location so existing importers keep working.
from db_mcp.tools.protocol import CRITICAL_REMINDER, inject_protocol  # noqa: E402, F401

# Commands allowed in the vault sandbox
ALLOWED_COMMANDS = {
    # Read operations
    "cat",
    "grep",
    "find",
    "ls",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "diff",
    # Write operations (append-only enforced by convention)
    "mkdir",
    "touch",
    "tee",
    # Utilities
    "echo",
    "date",
    "uuidgen",
}

# Patterns that are never allowed
BLOCKED_PATTERNS = [
    "rm ",
    "rm\t",
    "rmdir",  # No deletions
    "mv ",
    "mv\t",  # No moves (would lose history)
    "curl",
    "wget",  # No network
    "$(",
    "`",  # No command substitution
    "|sh",
    "|bash",
    "| sh",
    "| bash",  # No shell injection
    "..",  # No parent directory traversal
    "/.oauth",  # No access to OAuth secrets
]


@dataclass
class CommandValidation:
    """Result of command validation."""

    ok: bool
    message: str = ""
    is_write: bool = False


def validate_command(command: str) -> CommandValidation:
    """Validate bash command against security rules.

    Args:
        command: The bash command to validate

    Returns:
        CommandValidation with ok=True if allowed, or ok=False with error message
    """
    if not command or not command.strip():
        return CommandValidation(ok=False, message="Empty command")

    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            return CommandValidation(
                ok=False, message=f"Pattern '{pattern.strip()}' not allowed for security reasons"
            )

    # Check for overwrite redirection (> without <<)
    # Allow heredoc (<<) and append (>>), block single >
    if "> " in command or ">\t" in command:
        # Check if it's actually a heredoc or append
        if "<<" not in command and ">>" not in command:
            return CommandValidation(
                ok=False,
                message="Overwrite '>' not allowed. Use '<<' heredoc or '>>' append",
            )

    # Parse base command
    try:
        parts = shlex.split(command)
        base_cmd = parts[0] if parts else ""
    except ValueError:
        # shlex can't parse heredocs, extract command manually
        base_cmd = command.split()[0] if command.split() else ""

    if not base_cmd:
        return CommandValidation(ok=False, message="Could not parse command")

    if base_cmd not in ALLOWED_COMMANDS:
        return CommandValidation(
            ok=False,
            message=f"Command '{base_cmd}' not allowed. Permitted: {sorted(ALLOWED_COMMANDS)}",
        )

    # Detect write operations
    is_write = any(op in command for op in [">>", "<<", "tee ", "tee\t", "mkdir ", "touch "])

    return CommandValidation(ok=True, is_write=is_write)


async def run_sandboxed(command: str, cwd: Path, timeout: int = 30) -> dict:
    """Run a command in the sandboxed vault directory.

    Args:
        command: The bash command to run
        cwd: Working directory (must be vault path)
        timeout: Command timeout in seconds

    Returns:
        dict with stdout, stderr, and exit_code
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": str(cwd),
                "VAULT_PATH": str(cwd),
            },
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "exit_code": 124,
            }

        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": process.returncode,
        }

    except Exception as e:
        logger.exception("Error running sandboxed command")
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }


# Shell tool descriptions for different modes
SHELL_DESCRIPTION_DETAILED = """Run bash command in the knowledge vault.

A sandboxed bash interface for reading, searching, and appending knowledge.
The working directory is the vault root. All operations are append-only
(no deletions or overwrites allowed).

Available commands:
    - Read: cat, grep, find, ls, head, tail, wc, sort, uniq, diff
    - Write: mkdir, touch, tee (append-only)
    - Utils: echo, date, uuidgen

Examples:
    # Search for examples
    grep -ri "venue" examples/

    # Read instructions
    cat instructions/sql_rules.md

    # Find recent examples
    find examples -name "*.yaml" -mtime -7

Args:
    command: Bash command to execute in the vault

Returns:
    dict with stdout, stderr, exit_code
"""

SHELL_DESCRIPTION_SHELL_MODE = """YOUR PRIMARY TOOL - Use this for ALL query preparation.

START IMMEDIATELY with: cat PROTOCOL.md

This shell is your Swiss Army knife. The connection directory contains everything you need:

    connection/
    ├── PROTOCOL.md            # READ THIS FIRST - critical instructions
    ├── state.yaml             # Onboarding state
    ├── schema/
    │   └── descriptions.yaml  # Cached schema with descriptions
    ├── domain/
    │   └── model.md           # Domain model (business entities)
    ├── instructions/
    │   └── sql_rules.md       # SQL dialect rules
    ├── examples/              # Query examples (YAML)
    └── learnings/             # Patterns, common mistakes

WORKFLOW:
    1. cat PROTOCOL.md                              # Understand the rules
    2. cat schema/descriptions.yaml | head -100     # Check cached schema
    3. cat domain/model.md                          # Understand the domain
    4. grep -ri "keyword" examples/                 # Find similar queries
    5. cat instructions/sql_rules.md                # Check SQL rules
    6. Write SQL based on what you found
    7. Use validate_sql() then run_sql() to execute
    8. Save successful queries to examples/

Available commands:
    - Read: cat, grep, find, ls, head, tail, wc, sort, uniq, diff
    - Write: mkdir, touch, tee (append-only)
    - Utils: echo, date, uuidgen

Args:
    command: Bash command to execute in the connection directory

Returns:
    dict with stdout, stderr, exit_code
"""


async def _shell(command: str, connection: str) -> dict:
    """Run bash command in the connection directory - see SHELL_DESCRIPTION_* for docs."""
    from db_mcp.tools.utils import _resolve_connection_path

    resolved = _resolve_connection_path(connection)
    connection_path = Path(resolved)

    # Validate command
    validation = validate_command(command)
    if not validation.ok:
        logger.warning(f"Blocked command: {command} - {validation.message}")
        return {
            "stdout": "",
            "stderr": f"Error: {validation.message}",
            "exit_code": 1,
        }

    # Ensure connection directory exists
    if not connection_path.exists():
        return {
            "stdout": "",
            "stderr": f"Connection path does not exist: {connection_path}",
            "exit_code": 1,
        }

    # Run command
    logger.info(f"Running shell command: {command[:100]}...")
    result = await run_sandboxed(command, connection_path)

    # Reading protocol via shell counts as explicit acknowledgment for policy gating.
    if result["exit_code"] == 0 and "protocol.md" in command.lower():
        try:
            from db_mcp_data.execution.policy import record_protocol_ack

            record_protocol_ack(connection_path, source="shell")
        except Exception as exc:
            logger.debug(f"Failed to record protocol ack from shell: {exc}")

    # Log writes for audit
    if validation.is_write:
        logger.info(f"Connection write operation: {command[:100]}...")

    # Auto-inject protocol on first successful command
    if result["exit_code"] == 0:
        result = inject_protocol(result)

    return result


async def _protocol(connection: str) -> str:
    """Re-read the knowledge vault protocol.

    Use this if you need a reminder about:
    - Database hierarchy rules
    - How to save examples and learnings
    - User transparency requirements

    Returns:
        The full PROTOCOL.md content
    """
    from db_mcp.tools.utils import _resolve_connection_path

    resolved = _resolve_connection_path(connection)
    base_path = Path(resolved)

    protocol_path = base_path / "PROTOCOL.md"

    if protocol_path.exists():
        try:
            from db_mcp_data.execution.policy import record_protocol_ack

            record_protocol_ack(base_path, source="protocol_tool")
        except Exception as exc:
            logger.debug(f"Failed to record protocol ack: {exc}")
        return protocol_path.read_text()

    return "PROTOCOL.md not found. Connection may not be initialized."
