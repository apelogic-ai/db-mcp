"""Install lifecycle commands: uninstall and update."""

from __future__ import annotations

import json
import os
import platform
import shutil
import ssl
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi
import click
from rich.panel import Panel
from rich.prompt import Confirm

from db_mcp_cli.utils import (
    CONFIG_DIR,
    _get_cli_version,
    console,
)

REPO = "apelogic-ai/db-mcp"
DEFAULT_INSTALL_DIR = Path.home() / ".local" / "bin"
CACHE_DIR = CONFIG_DIR / "cache"


def _ssl_context() -> ssl.SSLContext:
    """Build an SSLContext using certifi's bundled CA store.

    Frozen PyInstaller binaries can't reach the system trust store, so
    `urlopen("https://...")` fails verification. Pointing OpenSSL at the
    certifi bundle (which ships with the Python wheel and is included in
    the PyInstaller bundle automatically) avoids that.
    """
    return ssl.create_default_context(cafile=certifi.where())


def _detect_platform() -> str:
    """Return the platform suffix used in release artifact names."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise click.ClickException(f"Unsupported architecture: {machine}")

    if system == "darwin":
        os_name = "macos"
    elif system == "linux":
        os_name = "linux"
    elif system.startswith(("win", "msys", "mingw", "cygwin")):
        os_name = "windows"
    else:
        raise click.ClickException(f"Unsupported operating system: {system}")

    return f"{os_name}-{arch}"


def _resolve_binary_path() -> Path:
    """Resolve the installed db-mcp binary path.

    Order:
      1. ``DB_MCP_INSTALL`` env var (matches install.sh)
      2. ``sys.argv[0]`` if it points at an existing file
      3. ``$PATH`` lookup for ``db-mcp``
      4. Fallback: ``~/.local/bin/db-mcp``
    """
    install_env = os.environ.get("DB_MCP_INSTALL", "").strip()
    if install_env:
        return Path(install_env).expanduser() / "db-mcp"

    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 and argv0.exists() and argv0.is_file():
        return argv0.resolve(strict=False)

    which_path = shutil.which("db-mcp")
    if which_path:
        return Path(which_path)

    return DEFAULT_INSTALL_DIR / "db-mcp"


def _fetch_latest_version(timeout: float = 5.0) -> tuple[str | None, str | None]:
    """Query GitHub for the latest release tag.

    Returns ``(version, error)`` where ``version`` is the tag without the 'v'
    prefix on success, or ``None`` with a human-readable ``error`` on failure.
    """
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return None, str(e)

    tag = data.get("tag_name") or ""
    if tag.startswith("v"):
        tag = tag[1:]
    return (tag or None), None


def _download_to(url: str, dest: Path, timeout: float = 60.0) -> None:
    """Download a URL to dest. Raises ClickException on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=_ssl_context()) as resp:
            if resp.status != 200:
                raise click.ClickException(
                    f"Download failed: HTTP {resp.status} for {url}"
                )
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
    except urllib.error.HTTPError as e:
        raise click.ClickException(f"Download failed: HTTP {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise click.ClickException(f"Download failed: {e} ({url})") from e

    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _install_binary(version: str, binary_path: Path) -> Path:
    """Install the binary for the given version. Returns the final binary path.

    On macOS we cache versioned binaries under ``CACHE_DIR`` and symlink, mirroring
    install.sh. On Linux/Windows the binary is downloaded directly to ``binary_path``.
    """
    plat = _detect_platform()
    ext = ".exe" if plat.startswith("windows-") else ""
    filename = f"db-mcp-{plat}{ext}"
    url = f"https://github.com/{REPO}/releases/download/v{version}/{filename}"

    console.print(f"[blue]Downloading db-mcp v{version} for {plat}...[/blue]")
    console.print(f"  URL: {url}")

    if plat.startswith("macos-"):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = CACHE_DIR / f"db-mcp-{version}{ext}"
        _download_to(url, cache_path)
        if binary_path.exists() or binary_path.is_symlink():
            binary_path.unlink()
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        binary_path.symlink_to(cache_path)

        # Strip macOS quarantine if present (install.sh does the same).
        try:
            subprocess.run(
                ["xattr", "-d", "com.apple.quarantine", str(cache_path)],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            pass
    else:
        _download_to(url, binary_path)

    return binary_path


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


@click.command("uninstall")
@click.option(
    "--purge",
    is_flag=True,
    help="Also delete ~/.db-mcp (config, connections, cached binaries, knowledge vault).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip interactive confirmations (DANGEROUS — deletes immediately).",
)
def uninstall_cmd(purge: bool, yes: bool) -> None:
    """Uninstall db-mcp. Removes the binary; --purge also wipes ~/.db-mcp.

    \b
    Examples:
      db-mcp uninstall                 Remove only the binary
      db-mcp uninstall --purge         Remove binary + all config/connections
      db-mcp uninstall --purge -y      Same, no confirmation prompts
    """
    binary_path = _resolve_binary_path()
    binary_target = binary_path.resolve(strict=False) if binary_path.exists() else binary_path

    summary_lines = [
        "[bold]Will remove:[/bold]",
        f"  • binary: [cyan]{binary_path}[/cyan]",
    ]
    if binary_path.is_symlink() and binary_target != binary_path:
        summary_lines.append(f"    → cached: [cyan]{binary_target}[/cyan]")
    if purge:
        summary_lines.append(f"  • config:  [cyan]{CONFIG_DIR}[/cyan]")
    console.print(Panel.fit("\n".join(summary_lines), border_style="yellow"))

    if not binary_path.exists() and not binary_path.is_symlink():
        if not purge:
            console.print("[yellow]No db-mcp binary found at the resolved path.[/yellow]")
            return
        console.print("[dim]No db-mcp binary found; will only purge config.[/dim]")

    if not yes:
        if not Confirm.ask("Proceed with uninstall?", default=False):
            console.print("[dim]Aborted.[/dim]")
            return
        if purge and not Confirm.ask(
            f"[red]Really delete {CONFIG_DIR}? This is irreversible.[/red]",
            default=False,
        ):
            console.print("[dim]Aborted.[/dim]")
            return

    # Remove binary (and cached target if symlink).
    if binary_path.is_symlink():
        try:
            binary_path.unlink()
            console.print(f"[green]Removed symlink:[/green] {binary_path}")
        except OSError as e:
            console.print(f"[red]Failed to remove {binary_path}: {e}[/red]")
        if binary_target.exists() and binary_target != binary_path:
            try:
                binary_target.unlink()
                console.print(f"[green]Removed cached binary:[/green] {binary_target}")
            except OSError as e:
                console.print(f"[red]Failed to remove {binary_target}: {e}[/red]")
    elif binary_path.exists():
        try:
            binary_path.unlink()
            console.print(f"[green]Removed binary:[/green] {binary_path}")
        except OSError as e:
            console.print(f"[red]Failed to remove {binary_path}: {e}[/red]")

    if purge and CONFIG_DIR.exists():
        try:
            shutil.rmtree(CONFIG_DIR)
            console.print(f"[green]Removed config dir:[/green] {CONFIG_DIR}")
        except OSError as e:
            console.print(f"[red]Failed to remove {CONFIG_DIR}: {e}[/red]")

    console.print("[bold green]✓ Uninstall complete.[/bold green]")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@click.command("update")
@click.option(
    "--check",
    is_flag=True,
    help="Only check for a newer version; do not install.",
)
@click.option(
    "--version",
    "version_override",
    default=None,
    help="Install a specific version (e.g. 0.9.11) instead of latest.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip the install confirmation prompt.",
)
def update_cmd(check: bool, version_override: str | None, yes: bool) -> None:
    """Check for and install a newer db-mcp release.

    \b
    Examples:
      db-mcp update                Check and install the latest release
      db-mcp update --check        Only check; print whether an update is available
      db-mcp update --version 0.9.11   Install a specific version
    """
    current = _get_cli_version()

    target: str | None
    if version_override:
        target = version_override.lstrip("v")
        console.print(f"Target version: [green]{target}[/green]  (current: {current})")
    else:
        console.print("Checking for the latest release...")
        target, fetch_error = _fetch_latest_version()
        if target is None:
            raise click.ClickException(
                f"Could not contact GitHub to determine the latest version: {fetch_error}"
            )
        console.print(f"Latest:  [green]{target}[/green]")
        console.print(f"Current: [cyan]{current}[/cyan]")

        if target == current:
            console.print("[bold green]✓ Already up to date.[/bold green]")
            return

    if check:
        console.print(f"[yellow]Update available: {current} → {target}[/yellow]")
        return

    if not yes and not Confirm.ask(
        f"Install db-mcp v{target} (replacing {current})?", default=True
    ):
        console.print("[dim]Aborted.[/dim]")
        return

    binary_path = _resolve_binary_path()
    _install_binary(target, binary_path)
    console.print(
        f"[bold green]✓ Installed db-mcp v{target}[/bold green] at "
        f"[cyan]{binary_path}[/cyan]"
    )
    console.print(
        "[dim]Run 'db-mcp --version' in a new shell to confirm.[/dim]"
    )


def register_commands(main_group: click.Group) -> None:
    """Register install lifecycle commands."""
    main_group.add_command(uninstall_cmd)
    main_group.add_command(update_cmd)
