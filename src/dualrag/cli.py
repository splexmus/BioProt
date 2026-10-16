from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from dualrag.config import load_config
from dualrag.io import write_json
from dualrag.pipeline import run_pipeline
from dualrag.reproducibility import compare_runs
from dualrag.storage import initialize_storage
from dualrag.tools import check_tools

app = typer.Typer(no_args_is_help=True, help="Dual-retrieval Phase 1 protein evidence pipeline.")


@app.command("run")
def run_command(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    input_path: Annotated[Path, typer.Option("--input", "-i", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    """Run configured retrieval channels, normalize them, and merge the evidence."""
    metadata = run_pipeline(load_config(config), input_path, output)
    typer.echo(
        f"run {metadata['run_id']} complete: {metadata['query_count']} queries, "
        f"{metadata['sequence_hit_count']} sequence hits, "
        f"{metadata['structure_hit_count']} structure hits -> {output}"
    )


@app.command("check-tools")
def check_tools_command() -> None:
    """Report optional external executable availability without requiring databases."""
    for status in check_tools():
        marker = "WARN" if status.warning else ("OK" if status.available else "MISSING")
        version = f" ({status.version})" if status.version else ""
        typer.echo(f"{marker:7} {status.name}: {status.executable}{version}")
        if status.warning:
            typer.echo(f"        {status.warning}")


@app.command("init-storage")
def init_storage_command(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
) -> None:
    """Create a configured storage tree and a non-destructive database manifest."""
    result = initialize_storage(load_config(config))
    free_gib = int(result["free_bytes"]) / (1024**3)
    typer.echo(f"storage ready at {result['data_root']} ({free_gib:.1f} GiB free)")
    typer.echo(f"database manifest: {result['manifest_path']}")


@app.command("compare-runs")
def compare_runs_command(
    first: Annotated[Path, typer.Option("--first", exists=True, file_okay=False)],
    second: Annotated[Path, typer.Option("--second", exists=True, file_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Compare stable biological outputs from two completed pipeline runs."""
    report = compare_runs(first, second)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, report)
    status = "equivalent" if report["equivalent"] else "different"
    typer.echo(f"runs are {status}: {first} vs {second}")
    if not report["equivalent"]:
        raise typer.Exit(code=1)
