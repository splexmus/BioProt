from __future__ import annotations

import runpy
from pathlib import Path


def test_external2go_keeps_only_non_root_molecular_function(tmp_path: Path) -> None:
    functions = runpy.run_path("scripts/build_phase3_mapping_resources.py")
    obo = tmp_path / "go.obo"
    obo.write_text(
        "[Term]\n"
        "id: GO:0000001\n"
        "namespace: molecular_function\n"
        "[Term]\n"
        "id: GO:0000002\n"
        "namespace: biological_process\n"
        "[Term]\n"
        "id: GO:0003674\n"
        "namespace: molecular_function\n",
        encoding="utf-8",
    )
    mapping = tmp_path / "interpro2go"
    mapping.write_text(
        "InterPro:IPR1 text > GO:first ; GO:0000001\n"
        "InterPro:IPR2 text > GO:second ; GO:0000002\n"
        "InterPro:IPR3 text > GO:root ; GO:0003674\n",
        encoding="utf-8",
    )

    allowed = functions["molecular_function_ids"](obo)
    rows = functions["external2go_rows"](mapping, "INTERPRO2GO", allowed)

    assert [row["target_id"] for row in rows] == ["GO:0000001"]
