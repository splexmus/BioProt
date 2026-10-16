from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from dualrag.structure.metadata import HEADER, build_metadata


def _gzip(path: Path, text: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)


def test_build_metadata_preserves_foldseek_targets_and_joins_annotations(
    tmp_path: Path,
) -> None:
    lookup = tmp_path / "pdb.lookup"
    lookup.write_text(
        "0\t1abc-assembly1_A\t0\n"
        "1\t1abc-assembly2_A-2\t1\n"
        "2\t2xyz-assembly1_B\t2\n"
        "3\tnot-a-pdb-target\t3\n"
        "4\t1abc-assembly1_A\t4\n",
        encoding="utf-8",
    )
    sifts_uniprot = tmp_path / "pdb_chain_uniprot.tsv.gz"
    _gzip(
        sifts_uniprot,
        "# 2026/10/04 | PDB: 40.26 | UniProt: 2026.03\n"
        "PDB\tCHAIN\tSP_PRIMARY\tRES_BEG\n"
        "1abc\tA\tP00001\t1\n"
        "1abc\tA\tP00002\t10\n"
        "1abc\tA\tP00001\t20\n",
    )
    sifts_interpro = tmp_path / "pdb_chain_interpro.tsv.gz"
    _gzip(
        sifts_interpro,
        "# 2026/10/04 | PDB: 40.26 | UniProt: 2026.03\n"
        "PDB\tCHAIN\tINTERPRO_ID\n"
        "1abc\tA\tIPR000002\n"
        "1abc\tA\tIPR000001\n",
    )
    swissprot = tmp_path / "uniprot_sprot.fasta.gz"
    _gzip(
        swissprot,
        ">sp|P00001|ONE_TEST First protein OS=Test organism OX=1\nMA\n"
        ">sp|P00002|TWO_TEST Second protein OS=Test organism OX=1\nMB\n",
    )
    output = tmp_path / "pdb_metadata.tsv"

    result = build_metadata(
        foldseek_lookup=lookup,
        sifts_uniprot=sifts_uniprot,
        sifts_interpro=sifts_interpro,
        swissprot_fasta=swissprot,
        output=output,
        work_dir=tmp_path,
    )

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert list(rows[0]) == HEADER
    assert rows[0] == {
        "target_structure_id": "1abc-assembly1_A",
        "target_uniprot_id": "P00001;P00002",
        "protein_name": "First protein;Second protein",
        "interpro_ids": "IPR000001;IPR000002",
        "supfam_ids": "",
        "structure_source": "PDB",
        "experimental_structure": "true",
        "source_accession": "1abc",
    }
    assert rows[1]["target_structure_id"] == "1abc-assembly2_A-2"
    assert rows[1]["target_uniprot_id"] == "P00001;P00002"
    assert rows[2]["target_uniprot_id"] == ""
    assert rows[3]["source_accession"] == ""
    assert result.target_count == 4
    assert result.uniprot_mapped_count == 2
    assert result.malformed_target_count == 1
    assert result.duplicate_target_count == 1
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["counts"]["targets_with_interpro"] == 2
    assert manifest["source_release_headers"]["pdb_chain_uniprot"].startswith(
        "2026/10/04"
    )
