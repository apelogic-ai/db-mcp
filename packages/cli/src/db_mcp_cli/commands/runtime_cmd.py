"""Non-MCP runtime commands for native code-mode execution."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import click
from db_mcp.code_runtime import CodeModeHost, build_runtime_contract, build_runtime_instructions
from db_mcp.code_runtime.http import start_runtime_server
from db_mcp.config import get_settings
from db_mcp.local_service import load_local_service_state, local_service_is_healthy
from db_mcp.orchestrator.engine import answer_intent
from fastmcp import FastMCP

from db_mcp_cli.commands.core import start as start_cmd


def _proxy_runtime_to_local_service(mcp_url: str) -> None:
    """Proxy stdio MCP traffic to the long-lived local db-mcp service."""
    proxy = FastMCP.as_proxy(mcp_url, name="db-mcp")
    proxy.run(show_banner=False)


@click.group("runtime", invoke_without_command=True)
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option(
    "--mode",
    type=click.Choice(["detailed", "shell", "exec-only", "code"]),
    default="code",
    show_default=True,
    help="MCP tool startup mode when runtime is used as the Claude/Desktop entrypoint.",
)
@click.option(
    "--interface",
    "runtime_interface",
    type=click.Choice(["native", "mcp", "cli"]),
    default=None,
    help=(
        "Runtime interface contract for the MCP runtime entrypoint "
        "(default: configured runtime_interface)"
    ),
)
@click.pass_context
def runtime_group(
    ctx: click.Context,
    connection: str | None,
    mode: str,
    runtime_interface: str | None,
) -> None:
    """Low-level runtime interface (MCP stdio or daemon)."""
    if ctx.invoked_subcommand is not None:
        return

    selected_interface = runtime_interface or get_settings().runtime_interface
    os.environ["RUNTIME_INTERFACE"] = selected_interface
    local_service = load_local_service_state()
    if local_service_is_healthy(local_service):
        mcp_url = str(local_service.get("mcp_url", "") or "")
        if mcp_url:
            _proxy_runtime_to_local_service(mcp_url)
            return
    callback = start_cmd.callback
    if callback is None:  # pragma: no cover - defensive guard
        raise click.ClickException("start command is unavailable")
    callback(connection, mode)


@runtime_group.command("prompt")
@click.option("-c", "--connection", required=True, help="Connection name")
@click.option(
    "--interface",
    "runtime_interface",
    type=click.Choice(["native", "mcp", "cli"]),
    default=None,
    help="Runtime interface contract to describe (default: configured runtime_interface)",
)
@click.option("--json", "as_json", is_flag=True, help="Emit structured contract JSON")
def runtime_prompt(connection: str, runtime_interface: str | None, as_json: bool) -> None:
    """Print the agent-facing native runtime contract."""
    selected_interface = runtime_interface or get_settings().runtime_interface
    if as_json:
        click.echo(
            json.dumps(
                build_runtime_contract(connection, interface=selected_interface),
                indent=2,
            )
            + "\n",
            nl=False,
        )
        return
    click.echo(build_runtime_instructions(connection, interface=selected_interface))


@runtime_group.command("run")
@click.option("-c", "--connection", required=True, help="Connection name")
@click.option("--code", "inline_code", help="Inline Python code to execute")
@click.option("--file", "code_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session-id", default=None, help="Stable runtime session id")
@click.option("--timeout-seconds", default=30, show_default=True, type=int)
@click.option("--confirmed", is_flag=True, help="Allow write statements for this execution")
@click.option("--json", "as_json", is_flag=True, help="Emit full structured result JSON")
def runtime_run(
    connection: str,
    inline_code: str | None,
    code_file: Path | None,
    session_id: str | None,
    timeout_seconds: int,
    confirmed: bool,
    as_json: bool,
) -> None:
    """Execute Python code in the shared db-mcp code runtime."""
    if bool(inline_code) == bool(code_file):
        raise click.UsageError("Provide exactly one of --code or --file.")

    host = CodeModeHost(connection=connection, session_id=session_id)
    if code_file is not None:
        result = host.run_file(
            code_file,
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
        )
    else:
        result = host.run(
            inline_code or "",
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
        )

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2) + "\n", nl=False)
        raise click.exceptions.Exit(result.exit_code)

    if result.stdout:
        click.echo(result.stdout, nl=not result.stdout.endswith("\n"))

    err_text = result.stderr or result.message or ""
    if err_text:
        click.echo(err_text, err=True, nl=not err_text.endswith("\n"))

    raise click.exceptions.Exit(result.exit_code)


def _load_code(inline_code: str | None, code_file: Path | None) -> str:
    if bool(inline_code) == bool(code_file):
        raise click.UsageError("Provide exactly one of --code or --file.")
    if code_file is not None:
        return code_file.read_text()
    return inline_code or ""


def _emit_runtime_result(result: dict[str, object], *, as_json: bool) -> None:
    exit_code = int(result.get("exit_code", 1) or 0)
    if as_json:
        click.echo(json.dumps(result, indent=2) + "\n", nl=False)
        raise click.exceptions.Exit(exit_code)

    stdout = str(result.get("stdout", "") or "")
    stderr = str(result.get("stderr", "") or result.get("message", "") or "")
    if stdout:
        click.echo(stdout, nl=not stdout.endswith("\n"))
    if stderr:
        click.echo(stderr, err=True, nl=not stderr.endswith("\n"))
    raise click.exceptions.Exit(exit_code)


def _parse_options_json(raw: str | None) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"Invalid JSON for --options-json: {exc}") from exc
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise click.UsageError("--options-json must decode to a JSON object.")
    return payload


def _parse_http_error(exc: HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    if not body:
        return f"Runtime server error: HTTP {exc.code}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
        if detail:
            return str(detail)
    return body


@runtime_group.command("exec")
@click.option("--server-url", required=True, help="Runtime server base URL")
@click.option("-c", "--connection", required=True, help="Connection name")
@click.option("--code", "inline_code", help="Inline Python code to execute")
@click.option("--file", "code_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session-id", required=True, help="Stable runtime session id")
@click.option("--timeout-seconds", default=30, show_default=True, type=int)
@click.option("--confirmed", is_flag=True, help="Allow write statements for this execution")
@click.option("--json", "as_json", is_flag=True, help="Emit full structured result JSON")
def runtime_exec(
    server_url: str,
    connection: str,
    inline_code: str | None,
    code_file: Path | None,
    session_id: str,
    timeout_seconds: int,
    confirmed: bool,
    as_json: bool,
) -> None:
    """Execute Python code through a persistent runtime server."""
    code = _load_code(inline_code, code_file)
    payload = {
        "connection": connection,
        "code": code,
        "session_id": session_id,
        "timeout_seconds": timeout_seconds,
        "confirmed": confirmed,
    }
    request = Request(
        f"{server_url.rstrip('/')}/api/runtime/run",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds + 5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise click.ClickException(_parse_http_error(exc)) from exc
    except URLError as exc:
        raise click.ClickException(f"Unable to reach runtime server: {exc.reason}") from exc

    _emit_runtime_result(result, as_json=as_json)


@runtime_group.command("intent")
@click.option("-c", "--connection", required=True, help="Connection name")
@click.option("--intent", "intent_text", required=True, help="Natural-language intent to resolve")
@click.option(
    "--options-json",
    default=None,
    help="Optional JSON object passed as answer_intent options",
)
@click.option("--json", "as_json", is_flag=True, help="Emit full structured result JSON")
def runtime_intent(
    connection: str,
    intent_text: str,
    options_json: str | None,
    as_json: bool,
) -> None:
    """Execute the shared semantic intent path from the CLI."""
    payload = asyncio.run(
        answer_intent(
            intent=intent_text,
            connection=connection,
            options=_parse_options_json(options_json),
        )
    )
    exit_code = 0 if payload.get("status") == "success" else 1

    if as_json:
        click.echo(json.dumps(payload, indent=2) + "\n", nl=False)
        raise click.exceptions.Exit(exit_code)

    text = str(payload.get("answer") or payload.get("error") or "")
    if text:
        click.echo(text)
    raise click.exceptions.Exit(exit_code)


@runtime_group.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind to")
@click.option("--port", default=8091, show_default=True, type=int, help="Port to listen on")
def runtime_serve(host: str, port: int) -> None:
    """Start the persistent runtime HTTP server."""
    start_runtime_server(host=host, port=port)


def register_commands(main_group: click.Group) -> None:
    """Register runtime commands with the main group."""
    main_group.add_command(runtime_group)
