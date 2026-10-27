from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from dualrag.calibration import run_confidence_calibration
from dualrag.config import load_config
from dualrag.io import write_json
from dualrag.literature.benchmark_queries import build_benchmark_literature_queries
from dualrag.literature.evaluation import (
    evaluate_literature,
    write_candidate_label_template,
    write_label_template,
)
from dualrag.literature.pipeline import run_literature_pipeline
from dualrag.literature.pubmed import PubMedConfig
from dualrag.literature.query_builder import build_literature_queries
from dualrag.pipeline import run_pipeline
from dualrag.rag.biological_evidence import enrich_evidence_packets
from dualrag.rag.ollama import OllamaClient, OllamaConfig
from dualrag.rag.pipeline import run_generation_pipeline
from dualrag.reproducibility import compare_runs
from dualrag.storage import initialize_storage
from dualrag.tools import check_tools

app = typer.Typer(no_args_is_help=True, help="Dual-retrieval protein evidence and fusion pipeline.")


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


@app.command("build-literature-queries")
def build_literature_queries_command(
    run_dir: Annotated[Path, typer.Option("--run", exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    context: Annotated[Path | None, typer.Option("--context", exists=True, dir_okay=False)] = None,
    max_candidates: Annotated[int, typer.Option("--max-candidates", min=1)] = 5,
    max_homologs: Annotated[int, typer.Option("--max-homologs", min=0)] = 5,
    max_alternatives: Annotated[int, typer.Option("--max-alternatives", min=0)] = 3,
) -> None:
    """Build deterministic Phase 4 literature queries from a completed biological run."""
    manifest = build_literature_queries(
        run_dir=run_dir,
        output_dir=output,
        context_path=context,
        max_candidates=max_candidates,
        max_homologs=max_homologs,
        max_alternatives=max_alternatives,
    )
    typer.echo(
        f"built {manifest['query_count']} literature queries from "
        f"run {manifest['source_run_id']} -> {output}"
    )


@app.command("run-literature")
def run_literature_command(
    queries: Annotated[Path, typer.Option("--queries", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    email: Annotated[str, typer.Option("--email", help="NCBI contact email")],
    tool: Annotated[str, typer.Option("--tool")] = "dualrag-bioprot",
    api_key_env: Annotated[str, typer.Option("--api-key-env")] = "NCBI_API_KEY",
    retmax: Annotated[int, typer.Option("--retmax", min=1, max=10000)] = 50,
    candidate_pool: Annotated[int, typer.Option("--candidate-pool", min=1)] = 100,
    top_k: Annotated[int, typer.Option("--top-k", min=1, max=20)] = 20,
    skip_pmc: Annotated[bool, typer.Option("--skip-pmc")] = False,
) -> None:
    """Run Phase 4.3-4.6 acquisition, chunking, retrieval, and packet creation."""
    manifest = run_literature_pipeline(
        queries_path=queries,
        output_dir=output,
        config=PubMedConfig(
            email=email,
            tool=tool,
            api_key_env=api_key_env,
            retmax_per_variant=retmax,
            candidate_pool_per_query=candidate_pool,
        ),
        fetch_pmc=not skip_pmc,
        top_k=top_k,
    )
    typer.echo(f"Phase {manifest['phase']} pipeline complete -> {output}")
    typer.echo("Scientific evaluation is pending manual Phase 4.7 labels.")


@app.command("build-literature-benchmark-queries")
def build_literature_benchmark_queries_command(
    dataset: Annotated[Path, typer.Option("--dataset", exists=True, file_okay=False)],
    phase3_run: Annotated[Path, typer.Option("--phase3-run", exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    split: Annotated[str, typer.Option("--split")] = "development",
    maximum_queries: Annotated[int, typer.Option("--maximum-queries", min=20)] = 20,
    go_obo: Annotated[Path | None, typer.Option("--go-obo", exists=True, dir_okay=False)] = None,
    ec2go: Annotated[Path | None, typer.Option("--ec2go", exists=True, dir_okay=False)] = None,
) -> None:
    """Build a leakage-safe >=20-query Phase 4 benchmark from Phase 3 artifacts."""
    manifest = build_benchmark_literature_queries(
        dataset_dir=dataset,
        phase3_run_dir=phase3_run,
        output_dir=output,
        split=split,
        maximum_queries=maximum_queries,
        go_obo_path=go_obo,
        ec2go_path=ec2go,
    )
    typer.echo(
        f"built {manifest['query_count']} {manifest['split']} literature benchmark queries "
        f"-> {output}"
    )


@app.command("make-literature-label-template")
def make_literature_label_template_command(
    output: Annotated[Path, typer.Option("--output", "-o")],
    hits: Annotated[Path | None, typer.Option("--hits", exists=True, dir_okay=False)] = None,
    candidates: Annotated[
        Path | None, typer.Option("--candidates", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Create a blank TSV for manual passage-level Phase 4.7 annotation."""
    if (hits is None) == (candidates is None):
        raise typer.BadParameter("provide exactly one of --hits or --candidates")
    if candidates is not None:
        write_candidate_label_template(candidates_path=candidates, output_path=output)
    else:
        assert hits is not None
        write_label_template(hits_path=hits, output_path=output)
    typer.echo(f"manual literature label template -> {output}")


@app.command("evaluate-literature")
def evaluate_literature_command(
    hits: Annotated[Path, typer.Option("--hits", exists=True, dir_okay=False)],
    labels: Annotated[Path, typer.Option("--labels", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    minimum_queries: Annotated[int, typer.Option("--minimum-queries", min=1)] = 20,
    candidates: Annotated[
        Path | None, typer.Option("--candidates", exists=True, dir_okay=False)
    ] = None,
    queries: Annotated[Path | None, typer.Option("--queries", exists=True, dir_okay=False)] = None,
    acceptance: Annotated[
        Path | None, typer.Option("--acceptance", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Evaluate Phase 4 retrieval against manually assigned passage labels."""
    result = evaluate_literature(
        hits_path=hits,
        labels_path=labels,
        output_dir=output,
        minimum_queries=minimum_queries,
        candidates_path=candidates,
        queries_path=queries,
        acceptance_path=acceptance,
    )
    typer.echo(
        f"literature evaluation: {result['status']} "
        f"({result['labeled_query_count']} labelled queries) -> {output}"
    )


@app.command("enrich-phase5-evidence")
def enrich_phase5_evidence_command(
    packets: Annotated[Path, typer.Option("--packets", exists=True, dir_okay=False)],
    sequence_evidence: Annotated[
        Path, typer.Option("--sequence-evidence", exists=True, dir_okay=False)
    ],
    structure_evidence: Annotated[
        Path, typer.Option("--structure-evidence", exists=True, dir_okay=False)
    ],
    output: Annotated[Path, typer.Option("--output", "-o")],
    manifest: Annotated[Path, typer.Option("--manifest")],
    max_per_modality: Annotated[int, typer.Option("--max-per-modality", min=1, max=5)] = 5,
    source_manifest: Annotated[
        Path | None, typer.Option("--source-manifest", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Add bounded sequence and structure records to Phase 5 evidence packets."""
    result = enrich_evidence_packets(
        packets_path=packets,
        sequence_evidence_path=sequence_evidence,
        structure_evidence_path=structure_evidence,
        output_path=output,
        manifest_path=manifest,
        max_per_modality=max_per_modality,
        source_manifest_path=source_manifest,
    )
    typer.echo(
        f"enriched {result['packet_count']} packets with "
        f"{result['modality_record_counts']} -> {output}"
    )


@app.command("init-ollama")
def init_ollama_command(
    model: Annotated[str, typer.Option("--model")] = "gemma3:4b",
    base_url: Annotated[str, typer.Option("--base-url")] = "http://127.0.0.1:11434",
    pull: Annotated[bool, typer.Option("--pull")] = False,
) -> None:
    """Check local Ollama and optionally pull the configured Phase 5 model."""
    client = OllamaClient(OllamaConfig(model=model, base_url=base_url, timeout_seconds=30))
    version = client.version()
    models = client.models()
    if model not in models and model.removesuffix(":latest") not in {
        item.removesuffix(":latest") for item in models
    }:
        if not pull:
            typer.echo(f"Ollama {version} is running, but model {model!r} is not installed")
            typer.echo(f"run again with --pull; installed models: {models}")
            raise typer.Exit(code=1)
        typer.echo(f"pulling {model} with Ollama {version}...")
        client.pull()
        models = client.models()
    typer.echo(f"Ollama {version} ready: model={model}; installed={models}")


@app.command("calibrate-confidence")
def calibrate_confidence_command(
    predictions: Annotated[Path, typer.Option("--predictions", exists=True, dir_okay=False)],
    candidates: Annotated[Path, typer.Option("--candidates", exists=True, dir_okay=False)],
    gold_labels: Annotated[Path, typer.Option("--gold-labels", exists=True, dir_okay=False)],
    splits: Annotated[Path, typer.Option("--splits", exists=True, dir_okay=False)],
    difficulty: Annotated[Path, typer.Option("--difficulty", exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option("--contract", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    """Fit and evaluate the Phase 6 development confidence calibrator."""
    result = run_confidence_calibration(
        predictions_path=predictions,
        candidates_path=candidates,
        gold_labels_path=gold_labels,
        splits_path=splits,
        difficulty_path=difficulty,
        contract_path=contract,
        output_dir=output,
    )
    manifest = result["manifest"]
    evaluation = result["evaluation"]["validation_calibrated"]
    typer.echo(
        f"Phase 6 calibrated {manifest['development_example_count']} development examples; "
        f"validation n={manifest['validation_example_count']}, "
        f"Brier={evaluation['brier_score']:.4f}, "
        f"ECE={evaluation['expected_calibration_error']:.4f} -> {output}"
    )


@app.command("generate-reports")
def generate_reports_command(
    packets: Annotated[Path, typer.Option("--packets", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    model: Annotated[str, typer.Option("--model")] = "gemma3:4b",
    base_url: Annotated[str, typer.Option("--base-url")] = "http://127.0.0.1:11434",
    temperature: Annotated[float, typer.Option("--temperature", min=0)] = 0.0,
    seed: Annotated[int, typer.Option("--seed")] = 42,
    timeout: Annotated[float, typer.Option("--timeout", min=1)] = 300.0,
    system_prompt: Annotated[
        Path, typer.Option("--system-prompt", exists=True, dir_okay=False)
    ] = Path("prompts/phase5-system-v3.txt"),
    report_prompt: Annotated[
        Path, typer.Option("--report-prompt", exists=True, dir_okay=False)
    ] = Path("prompts/phase5-report-v3.txt"),
    query_id: Annotated[list[str] | None, typer.Option("--query-id")] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    allow_unvalidated_phase4: Annotated[bool, typer.Option("--allow-unvalidated-phase4")] = False,
) -> None:
    """Generate and verify grounded Phase 5 reports with local Ollama."""
    manifest = run_generation_pipeline(
        packets_path=packets,
        output_dir=output,
        client=OllamaClient(
            OllamaConfig(
                model=model,
                base_url=base_url,
                timeout_seconds=timeout,
                temperature=temperature,
                seed=seed,
            )
        ),
        system_prompt_path=system_prompt,
        report_prompt_path=report_prompt,
        allow_unvalidated_phase4=allow_unvalidated_phase4,
        query_ids=set(query_id) if query_id else None,
        limit=limit,
    )
    typer.echo(
        f"Phase 5 generated {manifest['report_count']} reports with {manifest['model']} -> {output}"
    )
    typer.echo(f"verification: {manifest['verification_status_counts']}")
