from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from dualrag.config import load_config
from dualrag.pipeline import run_pipeline
from dualrag.tools import check_tools

app = typer.Typer(no_args_is_help=True, help="Dual-retrieval Phase 1 proof of concept.")


@app.command("run")
def run_command(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, dir_okay=False)],
    input_path: Annotated[Path, typer.Option("--input", "-i", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    """Run both fixture retrieval channels, normalize them, and merge the evidence."""
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
