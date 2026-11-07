from __future__ import annotations

import subprocess
from pathlib import Path


def test_all_processes_script_is_valid_and_keeps_scientific_stages_manual() -> None:
    path = Path("scripts/test_all_processes.sh")
    subprocess.run(["bash", "-n", str(path)], check=True)
    text = path.read_text(encoding="utf-8")
    assert "SAFE OFFLINE TEST: PASS" in text
    assert "Phase 3 scientific benchmark or any sealed test labels" in text
    assert "PubMed/PMC network acquisition" in text
