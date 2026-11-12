from __future__ import annotations

import shutil
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import requests

from dualrag.calibration.analysis import (
    build_analysis_calibration_report,
    load_validation_status,
    validation_explanation,
)
from dualrag.config import AppConfig
from dualrag.fasta import read_fasta
from dualrag.io import file_sha256, read_tsv, write_json
from dualrag.literature.packets import build_evidence_packets
from dualrag.literature.pipeline import run_literature_pipeline
from dualrag.literature.pubmed import PubMedConfig
from dualrag.literature.query_builder import build_literature_queries
from dualrag.literature.retrieval import retrieve_and_rerank
from dualrag.models import ProteinQuery
from dualrag.pipeline import run_pipeline
from dualrag.rag.biological_evidence import enrich_evidence_packets
from dualrag.rag.ollama import DEFAULT_OLLAMA_MODEL, OllamaClient, OllamaConfig
from dualrag.rag.pipeline import run_generation_pipeline
from dualrag.structure.alphafold import resolve_accession

UNIPROT_FASTA_URL = "https://rest.uniprot.org/uniprotkb/{accession}.fasta"


class AnalysisError(RuntimeError):
    pass


def run_analysis(
    *,
    config: AppConfig,
    output_dir: Path,
    fasta_path: Path | None = None,
    uniprot_accession: str | None = None,
    uniprot_url: str = UNIPROT_FASTA_URL,
    session: Any | None = None,
    literature: Literal["none", "local", "online"] = "none",
    literature_index: Path | None = None,
    literature_context: Path | None = None,
    email: str | None = None,
    api_key_env: str = "NCBI_API_KEY",
    report: Literal["none", "ollama"] = "none",
    allow_unvalidated_phase4: bool = False,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_timeout: float = 1800.0,
    max_output_tokens: int = 8192,
    ollama_client: OllamaClient | None = None,
    calibration_model: Path | None = None,
) -> dict[str, Any]:
    """Run biological retrieval with optional literature and grounded reporting."""
    if (fasta_path is None) == (uniprot_accession is None):
        raise AnalysisError("provide exactly one of --fasta or --uniprot")
    if calibration_model is not None and not calibration_model.is_file():
        raise AnalysisError("calibration model file does not exist")
    if literature == "local" and (literature_index is None or not literature_index.is_file()):
        raise AnalysisError("--literature local requires an existing --literature-index")
    if literature == "online" and not email:
        raise AnalysisError("--literature online requires --email for NCBI")
    if report == "ollama" and literature == "none":
        raise AnalysisError("--report ollama requires --literature local or online")
    if report == "ollama" and not allow_unvalidated_phase4:
        raise AnalysisError(
            "current Phase 4 is not scientifically validated; experimental reports require "
            "--allow-unvalidated-phase4"
        )
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise AnalysisError(f"output already exists; choose a new directory: {output_dir}")

    source_text: str | None = None
    source_url: str | None = None
    requested_accession: str | None = None
    if uniprot_accession is not None:
        requested_accession = _validate_accession(uniprot_accession)
        source_url = uniprot_url.format(accession=requested_accession)
        source_text = _fetch_uniprot(source_url, session=session)
        queries = _parse_fasta_text(source_text)
        if len(queries) != 1:
            raise AnalysisError("UniProt response must contain exactly one FASTA record")
        returned_accession, _ = resolve_accession(queries[0])
        if returned_accession != requested_accession:
            raise AnalysisError(
                f"UniProt returned accession {returned_accession!r}, "
                f"expected {requested_accession!r}"
            )
    else:
        assert fasta_path is not None
        fasta_path = fasta_path.resolve()
        if not fasta_path.is_file():
            raise AnalysisError(f"FASTA file does not exist: {fasta_path}")
        queries = read_fasta(fasta_path)

    output_dir.mkdir(parents=True)
    input_dir = output_dir / "input"
    biological_dir = output_dir / "biological"
    input_dir.mkdir()
    canonical_fasta = input_dir / "query.fasta"
    if source_text is not None:
        canonical_fasta.write_text(source_text, encoding="utf-8")
        source_type = "UNIPROT_ACCESSION"
    else:
        assert fasta_path is not None
        shutil.copyfile(fasta_path, canonical_fasta)
        source_type = "FASTA_FILE"

    manifest = {
        "schema_version": 1,
        "source_type": source_type,
        "requested_accession": requested_accession,
        "source_url": source_url,
        "retrieved_at": datetime.now(UTC).isoformat() if source_url else None,
        "fasta_sha256": file_sha256(canonical_fasta),
        "queries": [
            {
                "query_id": query.query_id,
                "sequence_length": len(query.sequence),
                "sequence_sha256": _sequence_sha256(query.sequence),
                "resolved_accession": resolve_accession(query)[0],
            }
            for query in queries
        ],
    }
    write_json(input_dir / "input_manifest.json", manifest)
    _write_status(output_dir, "RUNNING", "Biological retrieval is running")

    try:
        metadata = run_pipeline(config, canonical_fasta, biological_dir)
        calibration_manifest = build_analysis_calibration_report(
            biological_dir=biological_dir,
            output_dir=output_dir / "calibration",
            model_path=calibration_model,
        )
        summary = _build_summary(
            manifest, metadata, biological_dir, calibration_manifest=calibration_manifest
        )
        (output_dir / "summary.md").write_text(summary, encoding="utf-8")
        stages = {"biological": "COMPLETE", "literature": "SKIPPED", "report": "SKIPPED"}
        stages["calibration"] = "ASSESSMENT_COMPLETE"
        literature_manifest: dict[str, Any] | None = None
        generation_manifest: dict[str, Any] | None = None
        packets_path: Path | None = None
        if literature != "none":
            literature_dir = output_dir / "literature"
            query_dir = literature_dir / "queries"
            build_literature_queries(
                run_dir=biological_dir,
                output_dir=query_dir,
                context_path=literature_context,
            )
            queries_path = query_dir / "literature_queries.jsonl"
            if literature == "local":
                assert literature_index is not None
                literature_manifest = retrieve_and_rerank(
                    queries_path=queries_path,
                    index_path=literature_index,
                    output_dir=literature_dir,
                    top_k=20,
                )
                build_evidence_packets(
                    queries_path=queries_path,
                    hits_path=literature_dir / "literature_hits.jsonl",
                    output_dir=literature_dir,
                )
            else:
                assert email is not None
                literature_manifest = run_literature_pipeline(
                    queries_path=queries_path,
                    output_dir=literature_dir,
                    config=PubMedConfig(email=email, api_key_env=api_key_env),
                    fetch_pmc=True,
                    top_k=20,
                )
            packets_path = literature_dir / "evidence_packets.biological-v1.jsonl"
            enrich_evidence_packets(
                packets_path=literature_dir / "evidence_packets.jsonl",
                sequence_evidence_path=biological_dir / "sequence_results.tsv",
                structure_evidence_path=biological_dir / "structure_results.tsv",
                output_path=packets_path,
                manifest_path=literature_dir / "evidence_packets.biological-v1.manifest.json",
                max_per_modality=5,
                source_manifest_path=biological_dir / "run_metadata.json",
            )
            stages["literature"] = "COMPLETE"
        if report == "ollama":
            assert packets_path is not None
            generation_manifest = run_generation_pipeline(
                packets_path=packets_path,
                output_dir=output_dir / "report",
                client=ollama_client
                or OllamaClient(
                    OllamaConfig(
                        model=ollama_model,
                        base_url=ollama_base_url,
                        timeout_seconds=ollama_timeout,
                        num_predict=max_output_tokens,
                    )
                ),
                system_prompt_path=Path("prompts/phase5-system-v3.txt"),
                report_prompt_path=Path("prompts/phase5-report-v3.txt"),
                allow_unvalidated_phase4=allow_unvalidated_phase4,
                calibration_assessments={
                    row["query_id"]: row for row in calibration_manifest["queries"]
                },
            )
            stages["report"] = "COMPLETE"
        summary = _build_summary(
            manifest,
            metadata,
            biological_dir,
            literature_manifest=literature_manifest,
            generation_manifest=generation_manifest,
            calibration_manifest=calibration_manifest,
        )
        (output_dir / "summary.md").write_text(summary, encoding="utf-8")
        status = {
            "schema_version": 1,
            "status": "COMPLETE",
            "message": "Analysis and Phase 6 applicability assessment complete",
            "run_id": metadata["run_id"],
            "query_count": metadata["query_count"],
            "scientific_status": "PUTATIVE_HYPOTHESES_NOT_CALIBRATED",
            "confidence_status": "NOT_CALIBRATED",
            "calibration_gate_status": calibration_manifest["calibration_gate_status"],
            "benchmark_validation": calibration_manifest["benchmark_validation"],
            "decision_use": "HYPOTHESIS_GENERATION_ONLY",
            "stages": stages,
            "biological_output": str(biological_dir),
            "summary": str(output_dir / "summary.md"),
            "calibration_report": str(output_dir / "calibration/calibration_report.md"),
            "top_literature_report": (
                str(output_dir / "literature/top_literature.md") if literature != "none" else None
            ),
        }
        write_json(output_dir / "status.json", status)
        return status
    except Exception as exc:
        (output_dir / "analysis_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        _write_status(output_dir, "FAILED", str(exc))
        raise AnalysisError(str(exc)) from exc


def _validate_accession(value: str) -> str:
    accession = value.strip().upper()
    resolved, _ = resolve_accession(ProteinQuery(accession, "A"))
    if resolved != accession:
        raise AnalysisError(f"invalid supported UniProt accession: {value!r}")
    return accession


def _fetch_uniprot(url: str, *, session: Any | None) -> str:
    client = session or requests.Session()
    try:
        response = client.get(url, timeout=30)
    except requests.RequestException as exc:
        raise AnalysisError(f"UniProt request failed: {exc}") from exc
    if response.status_code == 404:
        raise AnalysisError("UniProt accession was not found")
    if response.status_code != 200:
        raise AnalysisError(f"UniProt request returned HTTP {response.status_code}")
    text = response.text
    if not text.lstrip().startswith(">"):
        raise AnalysisError("UniProt response is not FASTA")
    return text if text.endswith("\n") else text + "\n"


def _parse_fasta_text(text: str) -> list[ProteinQuery]:
    with tempfile.TemporaryDirectory(prefix="dualrag-uniprot-") as directory:
        path = Path(directory) / "query.fasta"
        path.write_text(text, encoding="utf-8")
        return read_fasta(path)


def _sequence_sha256(sequence: str) -> str:
    import hashlib

    return hashlib.sha256(sequence.encode()).hexdigest()


def _write_status(output_dir: Path, status: str, message: str) -> None:
    write_json(
        output_dir / "status.json",
        {
            "schema_version": 1,
            "status": status,
            "message": message,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def _build_summary(
    input_manifest: dict[str, Any],
    metadata: dict[str, object],
    biological_dir: Path,
    *,
    literature_manifest: dict[str, Any] | None = None,
    generation_manifest: dict[str, Any] | None = None,
    calibration_manifest: dict[str, Any] | None = None,
) -> str:
    validation = (
        calibration_manifest["benchmark_validation"]
        if calibration_manifest
        else load_validation_status()
    )
    summaries = read_tsv(biological_dir / "fusion_summary.tsv")
    sequence_hits = _hits_by_query(read_tsv(biological_dir / "sequence_results.tsv"))
    structure_hits = _hits_by_query(read_tsv(biological_dir / "structure_results.tsv"))
    lines = [
        "# BioProt analysis summary",
        "",
        f"Run ID: `{metadata['run_id']}`  ",
        "Scientific status: **putative hypotheses; confidence NOT_CALIBRATED**  ",
        f"Phase 6 benchmark calibration gate: **{validation['status']}**",
        "",
        "## Input",
        "",
        f"- Source: `{input_manifest['source_type']}`",
        f"- FASTA SHA-256: `{input_manifest['fasta_sha256']}`",
        f"- Query count: {metadata['query_count']}",
        "",
        "## Retrieval",
        "",
        f"- Sequence hits: {metadata['sequence_hit_count']}",
        f"- Structure hits: {metadata['structure_hit_count']}",
        "- AlphaFold structures are predicted structures, not experiments.",
        "",
        "## Function hypotheses",
        "",
    ]
    for row in summaries:
        query_id = row["query_id"]
        candidate = row.get("top_candidate_labels") or row.get("top_candidate_id") or "none"
        sequence = sequence_hits.get(query_id, [])
        structure = structure_hits.get(query_id, [])
        top_sequence = _top_hit(sequence)
        top_structure = _top_hit(structure)
        lines.extend(
            [
                f"### {query_id}",
                "",
                f"- Cross-modal state: `{row['cross_modal_status']}`",
                f"- Top candidate: {candidate}",
                f"- Provisional ranking score: {row.get('top_candidate_score') or 'N/A'} "
                "(not a probability)",
                f"- Interpretation: {row['classification_reason']}",
                "",
                "#### Sequence support",
                "",
                f"- Retrieved hits: {len(sequence)}",
                *(
                    [
                        f"- Top hit: `{top_sequence.get('target_id') or 'unknown'}` — "
                        f"{top_sequence.get('protein_name') or 'unlabelled protein'}",
                        "- Identity / coverage / E-value: "
                        f"{top_sequence.get('sequence_identity') or 'N/A'} / "
                        f"{top_sequence.get('alignment_coverage') or 'N/A'} / "
                        f"{top_sequence.get('evalue') or 'N/A'}",
                    ]
                    if top_sequence is not None
                    else ["- No sequence support was retrieved."]
                ),
                "",
                "#### Structure support",
                "",
                f"- Retrieved hits: {len(structure)}",
                *(
                    [
                        f"- Top hit: `{top_structure.get('target_structure_id') or 'unknown'}`"
                        f" — {top_structure.get('protein_name') or 'unlabelled protein'}",
                        "- TM-score / query coverage / target coverage: "
                        f"{top_structure.get('tm_score') or 'N/A'} / "
                        f"{top_structure.get('query_coverage') or 'N/A'} / "
                        f"{top_structure.get('target_coverage') or 'N/A'}",
                        "- Structure source: "
                        f"`{top_structure.get('structure_source') or 'unknown'}`; "
                        "experimental: "
                        f"`{top_structure.get('experimental_structure') or 'unknown'}`",
                    ]
                    if top_structure is not None
                    else ["- No structure support was retrieved."]
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Confidence and scientific boundary",
            "",
            "- Decision use: `HYPOTHESIS_GENERATION_ONLY`",
            "- Confidence status: `NOT_CALIBRATED`",
            *validation_explanation(validation),
            "- Calibrated probability: not emitted. The cohort calibrator is not valid for "
            "ordinary single-protein `analyze` output.",
            "- [Phase 6 assessment and model applicability](calibration/calibration_report.md)",
            "- Ranking scores order candidates; they do not measure experimental truth.",
            "",
            "## Literature and report",
            "",
            (
                f"- Literature retrieval: complete; hits: "
                f"{_manifest_count(literature_manifest, 'hit_count')}"
                if literature_manifest is not None
                else "- Literature retrieval: skipped"
            ),
            (
                f"- Ollama report: complete; reports: {generation_manifest['report_count']}"
                if generation_manifest is not None
                else "- Ollama report: skipped"
            ),
            "- Literature passages remain UNASSESSED unless manually labelled.",
            *(
                ["- [Top ranked literature passages](literature/top_literature.md)"]
                if literature_manifest is not None
                else []
            ),
            "",
            "## Next steps",
            "",
            "- Inspect `biological/sequence_results.tsv` and `structure_results.tsv` separately.",
            "- Review `biological/conflicts.tsv` and `alternatives.tsv`.",
            "- Build literature queries from the `biological/` directory if needed.",
            "- Do not describe this result as experimentally confirmed.",
            "",
        ]
    )
    return "\n".join(lines)


def _hits_by_query(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["query_id"], []).append(row)
    return grouped


def _top_hit(rows: list[dict[str, str]]) -> dict[str, str] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: float(row.get("normalized_score") or "-inf"))


def _manifest_count(manifest: dict[str, Any], key: str) -> object:
    if key in manifest:
        return manifest[key]
    retrieval = manifest.get("stages", {}).get("retrieval", {})
    return retrieval.get(key, "unknown") if isinstance(retrieval, dict) else "unknown"
