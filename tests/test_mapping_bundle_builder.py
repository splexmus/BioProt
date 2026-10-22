from __future__ import annotations

import csv
import gzip
import runpy
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "build_phase2_mapping_bundle.py"
BUILDER = runpy.run_path(str(SCRIPT))
_load_pfam_names = BUILDER["_load_pfam_names"]
_observed_pfam_candidates = BUILDER["_observed_pfam_candidates"]
_release_versions = BUILDER["_release_versions"]


def test_builder_parses_versioned_official_sources(tmp_path: Path) -> None:
    notes = tmp_path / "release-notes.txt"
    notes.write_text(
        "Release 110.0, 3rd September 2026\n"
        "Member database information\n"
        "              Pfam        38.2                    30134\n",
        encoding="utf-8",
    )
    clans = tmp_path / "Pfam-A.clans.tsv.gz"
    with gzip.open(clans, "wt", encoding="utf-8", newline="") as handle:
        handle.write("PF00042\tCL0090\tGlobin\tGlobin\tGlobin\n")

    assert _release_versions(notes) == ("110.0", "38.2")
    by_name, descriptions = _load_pfam_names(clans)
    assert by_name["Globin"] == ["PF00042"]
    assert descriptions["PF00042"] == "Globin"


def test_builder_reads_only_pfam_candidates(tmp_path: Path) -> None:
    candidates = tmp_path / "function_candidates.tsv"
    with candidates.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["candidate_id", "candidate_kind"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            [
                {"candidate_id": "PFAM:Globin", "candidate_kind": "PFAM"},
                {"candidate_id": "INTERPRO:IPR000971", "candidate_kind": "INTERPRO"},
            ]
        )

    assert _observed_pfam_candidates(candidates) == {"Globin"}
