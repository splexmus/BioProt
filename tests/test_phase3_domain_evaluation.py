from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate_phase3.py"
_domain_metrics = runpy.run_path(str(SCRIPT))["_domain_metrics"]


def test_domain_metrics_count_exact_mapping_aliases() -> None:
    candidates = [
        {
            "ablation": "ALL_MAPPINGS",
            "baseline": "B4_DUAL_DETERMINISTIC",
            "query_id": "sp|P1|TEST",
            "candidate_id": "INTERPRO:IPR013149",
            "candidate_aliases": "INTERPRO:IPR013149;PFAM:PF00107",
            "rerank_score": "0.8",
        }
    ]
    gold = [
        {"accession": "P1", "namespace": "INTERPRO", "identifier": "IPR013149"},
        {"accession": "P1", "namespace": "PFAM", "identifier": "PF00107"},
    ]

    metrics = _domain_metrics(candidates, gold, ["P1"])

    assert {row["metric"]: row["estimate"] for row in metrics} == {
        "interpro_exact_recall_at_10": 1.0,
        "pfam_exact_recall_at_10": 1.0,
    }
