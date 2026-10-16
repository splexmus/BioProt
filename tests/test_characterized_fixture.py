from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from dualrag.fasta import read_fasta

FIXTURES = Path(__file__).parent / "fixtures"


def test_characterized_fixture_matches_its_swissprot_manifest() -> None:
    queries = read_fasta(FIXTURES / "phase1_characterized.fasta")
    with (FIXTURES / "phase1_characterized_manifest.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        manifest = list(csv.DictReader(handle, delimiter="\t"))

    assert len(queries) == len(manifest) == 5
    by_id = {query.query_id: query for query in queries}
    assert set(by_id) == {row["fasta_id"] for row in manifest}
    assert len({row["taxonomy_id"] for row in manifest}) == 4

    for row in manifest:
        query = by_id[row["fasta_id"]]
        assert query.query_id.split("|")[1] == row["accession"]
        assert len(query.sequence) == int(row["sequence_length"])
        assert hashlib.sha256(query.sequence.encode()).hexdigest() == row["sequence_sha256"]
        assert row["source_database"] == "UniProtKB/Swiss-Prot"
        assert row["source_release"] == "2026_03"
        assert row["protein_existence"] == "1"
        assert row["interpro_ids"]
        assert row["pfam_ids"]
