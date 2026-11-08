from __future__ import annotations

import runpy
from pathlib import Path

from dualrag.config import load_config

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_phase3_benchmark.py"
RUNNER = runpy.run_path(str(SCRIPT))


def test_config_supplies_requested_benchmark_weights() -> None:
    config = load_config(
        Path(__file__).parents[1] / "config" / "4tb-hdd-interpro111-weights-v1.yaml"
    )

    assert RUNNER["_value"](None, config, "sequence_weight") == config.fusion.sequence_weight
    assert RUNNER["_value"](None, config, "agreement_weight") == config.fusion.agreement_weight
    assert RUNNER["_value"](0.6, config, "sequence_weight") == 0.6
