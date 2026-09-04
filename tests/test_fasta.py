from pathlib import Path

import pytest

from dualrag.fasta import read_fasta

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_fasta_preserves_order_and_description() -> None:
    queries = read_fasta(FIXTURES / "queries.fasta")
    assert [query.query_id for query in queries] == [
        "Q_CONSENSUS",
        "Q_SEQ_ONLY",
        "Q_STRUCT_ONLY",
        "Q_CONFLICT",
        "Q_EMPTY",
    ]
    assert queries[0].description == "synthetic consensus branch"


def test_read_fasta_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.fasta"
    path.write_text(">same\nMPEPTIDE\n>same another\nMPEPTIDE\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_fasta(path)
