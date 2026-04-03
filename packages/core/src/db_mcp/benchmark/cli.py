"""Standalone Click app for the benchmark harness."""

from __future__ import annotations

import json
import signal
from pathlib import Path

import click
from rich.console import Console

from db_mcp.benchmark.runner import (
    run_benchmark_suite_from_cli,
    run_preflight,
    summarize_run_directory,
)

console = Console()


@click.group()
def main():
    """db-mcp benchmark - standalone Claude Code comparison harness."""
    pass


def _render_progress(update: dict[str, object]) -> None:
    duration_seconds = float(update["duration_ms"]) / 1000
    console.print(
        f"[cyan]{update['completed_attempts']}/{update['total_attempts']}[/cyan] "
        f"{update['case_id']} "
        f"[magenta]{update['scenario']}[/magenta] "
        f"r{update['repeat']} "
        f"{update['result']} "
        f"duration={duration_seconds:.1f}s"
    )


@main.command()
@click.option("--connection", required=True, help="Connection name to benchmark.")
@click.option(
    "--case-pack",
    default="cases.yaml",
    show_default=True,
    help="Benchmark case-pack file under the connection benchmark directory.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable output.")
def preflight(connection: str, case_pack: str, as_json: bool):
    """Run benchmark preflight checks."""
    payload = run_preflight(connection, case_pack=case_pack)
    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        status = payload["status"]
        color = "green" if status == "pass" else "red"
        console.print(f"[bold {color}]preflight: {status}[/bold {color}]")
        for check in payload["checks"]:
            icon = "[green]✓[/green]" if check["status"] == "pass" else "[red]✗[/red]"
            console.print(f"  {icon} {check['name']}")
        if status != "pass":
            raise click.ClickException("Benchmark preflight failed.")


@main.command()
@click.option("--connection", required=True, help="Connection name to benchmark.")
@click.option("--model", required=True, help="Pinned Claude model id.")
@click.option(
    "--case-pack",
    default="cases.yaml",
    show_default=True,
    help="Benchmark case-pack file under the connection benchmark directory.",
)
@click.option("--cases", multiple=True, help="Optional case ids to run.")
@click.option(
    "--scenario",
    "scenarios",
    multiple=True,
    help="Optional benchmark scenario(s) to run, e.g. runtime_daemon.",
)
@click.option("--repeats", default=1, show_default=True, type=int, help="Repeat count per case.")
@click.option(
    "--output-root",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=Path.cwd() / "benchmark_runs",
    show_default=True,
    help="Directory where run artifacts will be written.",
)
@click.option("--seed", type=int, default=None, help="Optional shuffle seed.")
def run(
    connection: str,
    model: str,
    case_pack: str,
    cases: tuple[str, ...],
    scenarios: tuple[str, ...],
    repeats: int,
    output_root: Path,
    seed: int | None,
):
    """Run the benchmark suite."""
    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        run_dir = run_benchmark_suite_from_cli(
            connection=connection,
            model=model,
            case_pack=case_pack,
            cases=cases,
            scenarios=scenarios,
            repeats=repeats,
            output_root=output_root,
            seed=seed,
            progress_callback=_render_progress,
        )
    except KeyboardInterrupt as exc:
        raise click.Abort() from exc
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
    click.echo(f"Benchmark run saved to {run_dir}")


@main.command()
@click.argument("run_dir", type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable output.")
def summarize(run_dir: Path, as_json: bool):
    """Rebuild summaries for an existing run directory."""
    payload = summarize_run_directory(run_dir)
    if as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        console.print(f"[green]Attempts:[/green] {payload['totals']['attempts']}")
        for scenario, stats in payload["scenario_summary"].items():
            console.print(
                f"  [cyan]{scenario}[/cyan]: "
                f"{stats['correct']}/{stats['attempts']} correct, "
                f"avg {stats['avg_duration_ms']} ms"
            )
