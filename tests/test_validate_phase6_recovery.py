from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_validation_rejects_changed_model_before_opening_gold(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text('{"method":"logistic:0.01:1","parameters":{}}')
    output = tmp_path / "output"
    script = Path(__file__).parents[1] / "scripts/validate_phase6_recovery.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--dataset",
            str(tmp_path / "missing"),
            "--run",
            str(tmp_path / "missing"),
            "--model",
            str(model),
            "--ranking-profile",
            str(tmp_path / "missing"),
            "--gold-labels",
            str(tmp_path / "missing"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "saved recovery model changed" in result.stderr
    assert not output.exists()
