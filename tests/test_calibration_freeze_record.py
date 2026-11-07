from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_calibration_freeze_record_matches_contract() -> None:
    record = json.loads(
        Path("config/calibration-evaluation-v2.freeze.json").read_text(encoding="utf-8")
    )
    contract_path = Path(record["contract"]["path"])
    observed = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    assert observed == record["contract"]["sha256"]
    assert record["status"] == "THRESHOLDS_FROZEN_SYSTEM_NOT_YET_FROZEN"
    assert record["repository"]["worktree_dirty"] is True
    assert any("gemma4:more" in item for item in record["boundaries"])
