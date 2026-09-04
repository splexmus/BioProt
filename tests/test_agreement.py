from dualrag.fusion.agreement import compare
from dualrag.models import CrossModalStatus, SequenceEvidence, StructureEvidence


def sequence(**values: object) -> SequenceEvidence:
    defaults = dict(
        query_id="q",
        target_id="s",
        tool="test",
        tool_version="1",
        database="test",
        database_version="1",
    )
    return SequenceEvidence(**(defaults | values))  # type: ignore[arg-type]


def structure(**values: object) -> StructureEvidence:
    defaults = dict(
        query_id="q",
        target_structure_id="t",
        target_uniprot_id=None,
        tool="test",
        tool_version="1",
        database="test",
        database_version="1",
    )
    return StructureEvidence(**(defaults | values))  # type: ignore[arg-type]


def test_all_comparison_branches() -> None:
    assert compare(None, None)[0] is CrossModalStatus.INSUFFICIENT_EVIDENCE
    assert compare(sequence(), None)[0] is CrossModalStatus.SEQUENCE_ONLY
    assert compare(None, structure())[0] is CrossModalStatus.STRUCTURE_ONLY
    assert (
        compare(sequence(protein_name="Same name"), structure(protein_name="same-name"))[0]
        is CrossModalStatus.CONSENSUS
    )
    assert (
        compare(sequence(interpro_ids=["IPR1"]), structure(interpro_ids=["IPR1"]))[0]
        is CrossModalStatus.PARTIAL_CONSENSUS
    )
    assert (
        compare(sequence(protein_name="a"), structure(protein_name="b"))[0]
        is CrossModalStatus.CONFLICT
    )
