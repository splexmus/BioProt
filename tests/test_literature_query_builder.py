from __future__ import annotations

import json
from pathlib import Path

import pytest

from dualrag.io import write_json, write_tsv
from dualrag.literature.query_builder import build_literature_queries


def _make_run(root: Path, *, query_id: str = "sp|P69905|HBA_HUMAN") -> Path:
    run = root / "run"
    run.mkdir()
    write_tsv(
        run / "queries.tsv",
        [
            {
                "query_id": query_id,
                "description": "Hemoglobin subunit alpha",
                "sequence_length": 6,
                "sequence": "MVLSPA",
            }
        ],
        ["query_id", "description", "sequence_length", "sequence"],
    )
    candidates = [
        {
            "query_id": query_id,
            "candidate_id": "GO:0019825",
            "candidate_labels": "oxygen binding",
            "informative": "true",
            "rank": "1",
        },
        {
            "query_id": query_id,
            "candidate_id": "INTERPRO:IPR000971",
            "candidate_labels": "globin",
            "informative": "true",
            "rank": "2",
        },
        {
            "query_id": query_id,
            "candidate_id": "GO:0003674",
            "candidate_labels": "molecular function",
            "informative": "false",
            "rank": "3",
        },
    ]
    write_tsv(
        run / "function_candidates.tsv",
        candidates,
        ["query_id", "candidate_id", "candidate_labels", "informative", "rank"],
    )
    write_tsv(
        run / "fusion_summary.tsv",
        [{"query_id": query_id, "cross_modal_status": "CONSENSUS"}],
        ["query_id", "cross_modal_status"],
    )
    alternatives = [
        {
            "query_id": query_id,
            "rank": "1",
            "candidate_id": "GO:0019825",
            "candidate_labels": "oxygen binding",
        },
        {
            "query_id": query_id,
            "rank": "2",
            "candidate_id": "INTERPRO:IPR000971",
            "candidate_labels": "globin",
        },
    ]
    write_tsv(
        run / "alternatives.tsv",
        alternatives,
        ["query_id", "rank", "candidate_id", "candidate_labels"],
    )
    sequence_rows = [
        {
            "query_id": query_id,
            "target_id": "target-a",
            "source_accession": "P01942",
            "sequence_identity": "0.70",
            "alignment_coverage": "0.90",
            "normalized_score": "0.80",
            "tool": "MMseqs2",
            "tool_version": "16.747c6",
            "database": "Swiss-Prot",
            "database_version": "2026_03",
        },
        {
            "query_id": query_id,
            "target_id": "target-a-copy",
            "source_accession": "P01942",
            "sequence_identity": "0.69",
            "alignment_coverage": "0.88",
            "normalized_score": "0.79",
            "tool": "MMseqs2",
            "tool_version": "16.747c6",
            "database": "Swiss-Prot",
            "database_version": "2026_03",
        },
        {
            "query_id": query_id,
            "target_id": "target-b",
            "source_accession": "P02042",
            "sequence_identity": "0.55",
            "alignment_coverage": "0.85",
            "normalized_score": "0.70",
            "tool": "MMseqs2",
            "tool_version": "16.747c6",
            "database": "Swiss-Prot",
            "database_version": "2026_03",
        },
    ]
    write_tsv(run / "sequence_results.tsv", sequence_rows, list(sequence_rows[0]))
    write_json(
        run / "run_metadata.json",
        {
            "run_id": "run-1",
            "parameters_hash": "parameters-1",
            "created_at": "2026-10-26T00:00:00+00:00",
        },
    )
    return run


def _context(path: Path, *, include_gold: bool = False) -> Path:
    fields = ["query_id", "query_accession", "protein_name", "organism", "taxonomy_id"]
    row = {
        "query_id": "sp|P69905|HBA_HUMAN",
        "query_accession": "P69905",
        "protein_name": "Hemoglobin subunit alpha",
        "organism": "Homo sapiens",
        "taxonomy_id": "9606",
    }
    if include_gold:
        fields.append("gold_labels")
        row["gold_labels"] = "GO:0019825"
    write_tsv(path, [row], fields)
    return path


def test_builder_is_deterministic_and_uses_only_allowed_artifacts(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    context = _context(tmp_path / "context.tsv")
    output = tmp_path / "literature"

    manifest = build_literature_queries(
        run_dir=run,
        output_dir=output,
        context_path=context,
        max_candidates=2,
        max_homologs=2,
        max_alternatives=1,
    )
    first_queries = (output / "literature_queries.jsonl").read_bytes()
    first_manifest = (output / "literature_query_manifest.json").read_bytes()
    build_literature_queries(
        run_dir=run,
        output_dir=output,
        context_path=context,
        max_candidates=2,
        max_homologs=2,
        max_alternatives=1,
    )

    assert (output / "literature_queries.jsonl").read_bytes() == first_queries
    assert (output / "literature_query_manifest.json").read_bytes() == first_manifest
    record = json.loads(first_queries)
    assert record["query_accession"] == "P69905"
    assert record["candidate_ids"] == ["GO:0019825", "INTERPRO:IPR000971"]
    assert [item["accession"] for item in record["selected_homologs"]] == [
        "P01942",
        "P02042",
    ]
    assert record["alternative_hypotheses"] == ["INTERPRO:IPR000971: globin"]
    assert '"P69905" AND "oxygen binding" AND "Homo sapiens"' in record["query_variants"]
    assert manifest["prohibited_inputs_not_accessed"]
    assert "gold_labels.tsv" not in manifest["inputs"]


def test_context_schema_rejects_gold_label_column(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    context = _context(tmp_path / "context.tsv", include_gold=True)
    with pytest.raises(ValueError, match="unexpected=.*gold_labels"):
        build_literature_queries(
            run_dir=run,
            output_dir=tmp_path / "output",
            context_path=context,
        )


def test_context_rejects_invalid_uniprot_accession(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    context = _context(tmp_path / "context.tsv")
    text = context.read_text(encoding="utf-8").replace("\tP69905\t", "\tinvalid\t")
    context.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid UniProt query_accession"):
        build_literature_queries(
            run_dir=run,
            output_dir=tmp_path / "output",
            context_path=context,
        )


def test_unresolved_query_requires_explicit_context(tmp_path: Path) -> None:
    run = _make_run(tmp_path, query_id="custom-protein")
    with pytest.raises(ValueError, match="query_accession or protein_name"):
        build_literature_queries(run_dir=run, output_dir=tmp_path / "output")


def test_zero_optional_limits_emit_no_homologs_or_alternatives(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    output = tmp_path / "output"
    build_literature_queries(
        run_dir=run,
        output_dir=output,
        context_path=_context(tmp_path / "context.tsv"),
        max_homologs=0,
        max_alternatives=0,
    )
    record = json.loads((output / "literature_queries.jsonl").read_text(encoding="utf-8"))
    assert record["selected_homologs"] == []
    assert record["alternative_hypotheses"] == []
