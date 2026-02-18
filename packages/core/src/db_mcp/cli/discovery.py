"""Schema discovery orchestration for the db-mcp CLI.

Runs connector-based schema discovery with Rich progress indicators
in a background thread with a configurable timeout.
"""

import threading
import time

from rich.console import Console

from db_mcp.cli.utils import console


def _run_discovery_with_progress(
    connector,
    conn_name: str = "cli-discover",
    save: bool = False,
    timeout_s: int = 300,
    schemas: list[str] | None = None,
) -> dict | None:
    """Run schema discovery with Rich progress indicators.

    Args:
        connector: Database connector instance
        conn_name: Connection name (used for schema file if saving)
        save: If True, save schema_descriptions.yaml to the connection dir
        timeout_s: Abort if discovery takes longer than this many seconds
        schemas: Optional list of schema names to limit discovery

    Returns:
        Dict with discovered tables info, or None on failure
    """
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    from db_mcp.onboarding.schema_store import create_initial_schema

    err_console = Console(stderr=True)
    all_tables: list[dict] = []
    dialect: str | None = None

    # NOTE: SIGALRM cannot reliably interrupt blocking DBAPI calls (e.g., psycopg2),
    # so we run the whole discovery in a daemon thread with a hard deadline.

    err_console.print("[dim]Starting discovery...[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=err_console,
    ) as progress:
        # Start spinner immediately so the user sees *something* before any blocking calls.
        task = progress.add_task("Starting discovery...", total=None)
        progress.refresh()

        result: list[dict | None] = [None]
        error: list[Exception | None] = [None]

        def run() -> None:
            try:
                # Phase 1: Connect
                test_result = connector.test_connection()
                if not test_result.get("connected"):
                    error[0] = RuntimeError(test_result.get("error", "unknown"))
                    return

                nonlocal dialect
                dialect = test_result.get("dialect")
                progress.update(task, description="Connected ✓", completed=1, total=1)

                # Phase 2: Catalogs
                progress.update(
                    task, description="Discovering catalogs...", completed=0, total=None
                )
                try:
                    catalogs = connector.get_catalogs()
                except Exception:
                    catalogs = [None]
                progress.update(
                    task,
                    description=f"Found {len([c for c in catalogs if c])} catalogs ✓",
                    completed=1,
                    total=1,
                )

                # Phase 3: Schemas
                progress.update(
                    task, description="Discovering schemas...", completed=0, total=None
                )
                all_schemas: list[dict] = []
                for catalog in catalogs:
                    try:
                        found = connector.get_schemas(catalog=catalog)
                    except Exception:
                        found = []

                    for schema in found:
                        if schemas and schema not in schemas:
                            continue
                        all_schemas.append({"catalog": catalog, "schema": schema})

                progress.update(
                    task,
                    description=f"Found {len(all_schemas)} schemas ✓",
                    completed=1,
                    total=1,
                )

                # Phase 4: Tables + columns (progress per table)
                progress.remove_task(task)
                table_task = progress.add_task("Scanning tables...", total=1)

                total_tables = 0
                for schema_info in all_schemas:
                    catalog = schema_info["catalog"]
                    schema = schema_info["schema"]
                    label = f"{catalog}.{schema}" if catalog else (schema or "default")
                    progress.update(
                        table_task,
                        description=f"Listing tables in {label}...",
                        total=None,
                    )

                    try:
                        tables = connector.get_tables(schema=schema, catalog=catalog)
                    except Exception:
                        tables = []

                    # update total now that we know table count for this schema
                    total_tables += len(tables)
                    progress.update(table_task, total=max(total_tables, 1))

                    for t in tables:
                        progress.update(
                            table_task,
                            description=f"Scanning {t.get('full_name') or t.get('name')}...",
                        )
                        try:
                            columns = connector.get_columns(
                                t["name"], schema=schema, catalog=catalog
                            )
                        except Exception:
                            columns = []
                        all_tables.append(
                            {
                                "name": t["name"],
                                "schema": schema,
                                "catalog": catalog,
                                "full_name": t.get("full_name") or t["name"],
                                "columns": columns,
                            }
                        )
                        progress.advance(table_task)

                result[0] = {
                    "tables": all_tables,
                    "total_columns": sum(len(t["columns"]) for t in all_tables),
                    "dialect": dialect,
                }
            except Exception as e:
                error[0] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()

        deadline = time.monotonic() + timeout_s if timeout_s and timeout_s > 0 else None

        while True:
            # Timeout handling
            if deadline is not None and time.monotonic() > deadline:
                console.print(f"[red]Discovery timed out after {timeout_s}s[/red]")
                return None

            # Allow Rich to refresh while the worker thread runs.
            progress.refresh()
            time.sleep(0.1)

            # Exit when worker finishes
            if not t.is_alive():
                break

        if error[0] is not None:
            console.print(f"[red]Discovery failed: {error[0]}[/red]")
            return None

        if result[0] is None:
            console.print("[red]Discovery failed: unknown error[/red]")
            return None

    total_columns = sum(len(t["columns"]) for t in all_tables)
    err_console.print(
        f"[green]Done![/green] Found [bold]{len(all_tables)}[/bold] tables "
        f"with [bold]{total_columns}[/bold] columns."
    )

    # Build schema object
    schema_obj = create_initial_schema(
        provider_id=conn_name,
        dialect=dialect,
        tables=all_tables,
    )

    # Optionally save to connection directory
    if save:
        from db_mcp.onboarding.schema_store import save_schema_descriptions

        schema_obj.provider_id = conn_name
        save_result = save_schema_descriptions(schema_obj)
        if save_result.get("saved"):
            err_console.print(f"[green]✓ Schema saved to {save_result.get('file_path')}[/green]")

    return {
        "tables": all_tables,
        "total_columns": total_columns,
        "dialect": dialect,
        "schema": schema_obj,
    }
