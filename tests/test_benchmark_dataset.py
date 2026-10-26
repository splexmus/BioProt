from __future__ import annotations

import csv
from pathlib import Path

from dualrag.benchmark.dataset import (
    assign_cluster_splits,
    build_leakage_outputs,
    is_eligible,
    parse_swissprot,
)
from dualrag.benchmark.panel import parse_panel_markdown


def test_parse_swissprot_preserves_experimental_label_provenance(tmp_path: Path) -> None:
    source = tmp_path / "sample.dat"
    source.write_text(
        """ID   TEST_HUMAN              Reviewed;          40 AA.
AC   P00001;
DT   01-JAN-2000, integrated into UniProtKB/Swiss-Prot.
DT   01-JAN-2000, sequence version 1.
DT   02-SEP-2026, entry version 7.
DE   RecName: Full=Test enzyme;
DE            EC=1.2.3.4 {ECO:0000269|PubMed:123456};
OS   Homo sapiens (Human).
OC   Eukaryota; Metazoa.
OX   NCBI_TaxID=9606;
DR   GO; GO:0003824; F:catalytic activity; IDA:UniProtKB.
DR   InterPro; IPR000001; Test_domain.
DR   Pfam; PF00001; Test; 1.
FT   ACT_SITE       12
FT                   /evidence="ECO:0000269|PubMed:123456"
PE   1: Evidence at protein level;
SQ   SEQUENCE   40 AA;  4000 MW;  0000000000000000 CRC64;
     ACDEFGHIKL MNPQRSTVWY ACDEFGHIKL MNPQRSTVWY
//
""",
        encoding="utf-8",
    )

    entry = next(parse_swissprot(source))

    assert entry.accession == "P00001"
    assert entry.superkingdom == "Eukaryota"
    assert entry.entry_version == "7"
    assert is_eligible(entry, 40, 2000)
    assert [(label.namespace, label.identifier) for label in entry.labels] == [
        ("EC", "1.2.3.4"),
        ("GO_MF", "GO:0003824"),
    ]
    assert entry.labels[0].supporting_reference == "PMID:123456"
    assert entry.labels[0].admissible_for_primary is True
    assert entry.interpro_ids == ["IPR000001"]
    assert entry.pfam_ids == ["PF00001"]
    assert entry.active_site_count == 1


def test_parse_panel_markdown_preserves_supplied_groups(tmp_path: Path) -> None:
    panel = tmp_path / "panel.md"
    panel.write_text(
        """## Archaea

| Accession | Protein | Biological role | Site | Architecture |
|---|---|---|---|---|
| `Q5JIZ8` | Example protein | Example role | Low-site | Single* |
""",
        encoding="utf-8",
    )

    candidates = parse_panel_markdown(panel)

    assert len(candidates) == 1
    assert candidates[0].accession == "Q5JIZ8"
    assert candidates[0].supplied_taxonomy_group == "Archaea"
    assert candidates[0].supplied_architecture == "Single"


def test_cluster_split_keeps_every_cluster_intact_and_is_deterministic() -> None:
    clusters = {"A": ["A", "B"], "C": ["C"], "D": ["D"], "E": ["E"]}
    ratios = {"development": 0.70, "validation": 0.15, "test": 0.15}

    first = assign_cluster_splits(clusters, 42, ratios)
    second = assign_cluster_splits(clusters, 42, ratios)

    assert first == second
    assert set(first) == set(clusters)
    assert set(first.values()) <= set(ratios)


def test_leakage_and_difficulty_use_only_allowed_references(tmp_path: Path) -> None:
    source = tmp_path / "sample.dat"
    source.write_text(
        """ID   TEST_HUMAN              Reviewed;          40 AA.
AC   P00001;
DT   02-SEP-2026, entry version 7.
DE   RecName: Full=Test enzyme;
DE            EC=1.2.3.4 {ECO:0000269|PubMed:123456};
OS   Homo sapiens (Human).
OC   Eukaryota; Metazoa.
OX   NCBI_TaxID=9606;
PE   1: Evidence at protein level;
SQ   SEQUENCE   40 AA;  4000 MW;  0000000000000000 CRC64;
     ACDEFGHIKL MNPQRSTVWY ACDEFGHIKL MNPQRSTVWY
//
""",
        encoding="utf-8",
    )
    entry = next(parse_swissprot(source))
    alignments = tmp_path / "alignments.tsv"
    with alignments.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["query", "target", "fident", "qcov", "tcov", "evalue", "bits"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "query": entry.fasta_id,
                "target": entry.fasta_id,
                "fident": "1.0",
                "qcov": "1.0",
                "tcov": "1.0",
                "evalue": "0",
                "bits": "100",
            }
        )
        writer.writerow(
            {
                "query": entry.fasta_id,
                "target": "sp|P99999|ALLOWED",
                "fident": "0.62",
                "qcov": "0.8",
                "tcov": "0.8",
                "evalue": "1e-20",
                "bits": "80",
            }
        )

    prohibited, difficulty = build_leakage_outputs(
        alignments, [entry], {entry.accession: entry.sequence_sha256}, tmp_path
    )

    assert prohibited[0]["exclusion_reason"] == "EXACT_ACCESSION"
    assert difficulty[0]["closest_allowed_reference"] == "P99999"
    assert difficulty[0]["difficulty_stratum"] == "FROM_50_TO_70"
