from __future__ import annotations

import shutil
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from dualrag.config import AppConfig
from dualrag.fasta import read_fasta
from dualrag.io import file_sha256, read_tsv, write_json
from dualrag.models import ProteinQuery
from dualrag.pipeline import run_pipeline
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
) -> dict[str, Any]:
    """Validate one input source, run Phase 1-2, and write a deterministic summary."""
    if (fasta_path is None) == (uniprot_accession is None):
        raise AnalysisError("provide exactly one of --fasta or --uniprot")
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
        summary = _build_summary(manifest, metadata, biological_dir)
        (output_dir / "summary.md").write_text(summary, encoding="utf-8")
        status = {
            "schema_version": 1,
            "status": "COMPLETE",
            "message": "Phase 1-2 analysis complete",
            "run_id": metadata["run_id"],
            "query_count": metadata["query_count"],
            "scientific_status": "PUTATIVE_HYPOTHESES_NOT_CALIBRATED",
            "biological_output": str(biological_dir),
            "summary": str(output_dir / "summary.md"),
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
    input_manifest: dict[str, Any], metadata: dict[str, object], biological_dir: Path
) -> str:
    summaries = read_tsv(biological_dir / "fusion_summary.tsv")
    lines = [
        "# BioProt analysis summary",
        "",
        f"Run ID: `{metadata['run_id']}`  ",
        "Scientific status: **putative hypotheses; confidence NOT_CALIBRATED**",
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
        candidate = row.get("top_candidate_labels") or row.get("top_candidate_id") or "none"
        lines.extend(
            [
                f"### {row['query_id']}",
                "",
                f"- Cross-modal state: `{row['cross_modal_status']}`",
                f"- Top candidate: {candidate}",
                f"- Ranking score: {row.get('top_candidate_score') or 'N/A'}",
                f"- Interpretation: {row['classification_reason']}",
                "",
            ]
        )
    lines.extend(
        [
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
