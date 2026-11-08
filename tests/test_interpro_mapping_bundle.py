from __future__ import annotations

import gzip
import runpy
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "build_interpro_pfam_mapping_bundle.py"
BUILDER = runpy.run_path(str(SCRIPT))


def test_full_mapping_parser_builds_accession_and_name_rows(tmp_path: Path) -> None:
    xml_path = tmp_path / "interpro.xml.gz"
    with gzip.open(xml_path, "wt", encoding="utf-8") as handle:
        handle.write(
            "<interprodb><release>"
            '<dbinfo version="111.0" dbname="INTERPRO"/>'
            '<dbinfo version="39.0" dbname="PFAM"/>'
            "</release>"
            '<interpro id="IPR013149"><member_list>'
            '<db_xref db="PFAM" dbkey="PF00107" name="ADH_zinc_N"/>'
            "</member_list></interpro></interprodb>"
        )
    clans_path = tmp_path / "Pfam-A.clans.tsv.gz"
    with gzip.open(clans_path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("PF00107\tCL0063\t\tADH_zinc_N\tZinc-binding dehydrogenase\n")

    integrations, versions = BUILDER["_interpro_integrations"](xml_path)
    names = BUILDER["_pfam_names"](clans_path)
    rows, ambiguous = BUILDER["_mapping_rows"](
        integrations, names, "InterPro 111.0; Pfam 39.0"
    )

    assert versions["INTERPRO"] == "111.0"
    assert versions["PFAM"] == "39.0"
    assert ambiguous == []
    assert {row["source_candidate_id"] for row in rows} == {
        "PFAM:PF00107",
        "PFAM:ADH_zinc_N",
    }
    assert {row["canonical_candidate_id"] for row in rows} == {"INTERPRO:IPR013149"}


def test_ambiguous_short_name_is_excluded_but_accessions_remain() -> None:
    rows, ambiguous = BUILDER["_mapping_rows"](
        {"PF00001": "IPR000001", "PF00002": "IPR000002"},
        {"PF00001": "duplicate", "PF00002": "duplicate"},
        "InterPro test; Pfam test",
    )

    assert ambiguous == ["PFAM:duplicate"]
    assert {row["source_candidate_id"] for row in rows} == {"PFAM:PF00001", "PFAM:PF00002"}
