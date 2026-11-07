from __future__ import annotations

from pathlib import Path

import pytest

from dualrag.benchmark.step3 import read_nomination_sources


def test_nomination_reviewed_status_uses_only_reviewed_column(tmp_path: Path) -> None:
    source = tmp_path / "v2.tsv"
    source.write_text(
        "Entry\tReviewed\tProtein existence\tAnnotation\n"
        "P00001\treviewed\tPredicted\t1.0\n"
        "P00002\tunreviewed\tEvidence at protein level\t5.0\n",
        encoding="utf-8",
    )

    records = read_nomination_sources([source])

    assert records[0].accepted_as_reviewed is True
    assert records[1].accepted_as_reviewed is False


def test_nomination_source_rejects_duplicate_accessions(tmp_path: Path) -> None:
    source = tmp_path / "source.tsv"
    source.write_text(
        "Entry\tReviewed\nP00001\treviewed\nP00001\treviewed\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate accession"):
        read_nomination_sources([source])


def test_nomination_source_requires_reviewed_column(tmp_path: Path) -> None:
    source = tmp_path / "source.tsv"
    source.write_text("Entry\nP00001\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Reviewed column"):
        read_nomination_sources([source])
