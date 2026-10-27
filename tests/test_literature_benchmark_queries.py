from __future__ import annotations

import json
from pathlib import Path

from dualrag.literature.benchmark_queries import (
    BENCHMARK_QUERY_BUILDER_VERSION,
    _benchmark_variants,
    build_benchmark_literature_queries,
)

ROOT = Path(__file__).parents[1]


def test_builds_twenty_leakage_safe_development_queries(tmp_path: Path) -> None:
    manifest = build_benchmark_literature_queries(
        dataset_dir=ROOT / "benchmark/phase3-pilot-v1",
        phase3_run_dir=ROOT / "benchmark/phase3-pipeline-v2-conservative",
        output_dir=tmp_path,
        split="development",
        maximum_queries=20,
        go_obo_path=ROOT / "benchmark/phase3-mappings-v1/sources/go-basic.obo",
        ec2go_path=ROOT / "benchmark/phase3-mappings-v1/sources/ec2go",
    )
    records = [
        json.loads(line)
        for line in (tmp_path / "literature_queries.jsonl").read_text().splitlines()
    ]
    assert manifest["query_count"] == 20
    assert len(records) == 20
    assert all(record["query_accession"] and record["protein_name"] for record in records)
    assert all(len(record["query_variants"]) >= 3 for record in records)
    assert str(ROOT / "benchmark/phase3-pilot-v1/gold_labels.tsv") not in manifest["inputs"]
    assert any("activity" in label for record in records for label in record["candidate_labels"])
    assert all(
        record["query_builder_version"] == BENCHMARK_QUERY_BUILDER_VERSION for record in records
    )
    assert all(f'"{record["protein_name"]}"' in record["query_variants"] for record in records)


def test_benchmark_variants_include_bounded_name_and_taxon_fallbacks() -> None:
    variants = _benchmark_variants(
        accession="I6WXK4",
        protein_name="Triple specificity protein phosphatase PtpB",
        organism="Mycobacterium tuberculosis (strain ATCC 25618 / H37Rv)",
        candidate_ids=["GO:0004725"],
        candidate_labels=["protein tyrosine phosphatase activity"],
        homologs=[],
    )

    assert '"Triple specificity protein phosphatase PtpB"' in variants
    assert '"PtpB" AND "Mycobacterium tuberculosis"' in variants
    assert '"PtpB"' in variants
    assert len(variants) <= 20


def test_benchmark_variants_include_conservative_descriptive_aliases() -> None:
    reverse_gyrase = _benchmark_variants(
        accession="F1SVH1",
        protein_name="Reverse gyrase subunit B",
        organism="Methanopyrus kandleri (strain AV19)",
        candidate_ids=[],
        candidate_labels=[],
        homologs=[],
    )
    aldolase_phosphatase = _benchmark_variants(
        accession="A8A9E4",
        protein_name="Fructose-1,6-bisphosphate aldolase/phosphatase",
        organism="Ignicoccus hospitalis (strain KIN4/I)",
        candidate_ids=[],
        candidate_labels=[],
        homologs=[],
    )
    heterodisulfide_reductase = _benchmark_variants(
        accession="A0A0E3NEE1",
        protein_name=("Dihydromethanophenazine:CoB--CoM heterodisulfide reductase subunit D"),
        organism="Methanosarcina thermophila (strain TM-1)",
        candidate_ids=[],
        candidate_labels=[],
        homologs=[],
    )

    assert '"Reverse gyrase" AND "Methanopyrus kandleri"' in reverse_gyrase
    assert '"aldolase/phosphatase"' in aldolase_phosphatase
    assert (
        '"heterodisulfide reductase" AND "Methanosarcina thermophila"' in heterodisulfide_reductase
    )
