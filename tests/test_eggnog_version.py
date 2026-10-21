from __future__ import annotations

import subprocess
import tempfile

from dualrag.sequence import eggnog


def test_eggnog_version_is_queried_outside_git_checkout(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        assert kwargs["cwd"] == tempfile.gettempdir()
        return subprocess.CompletedProcess(args[0], 0, "emapper-2.1.15\n", "")

    monkeypatch.setattr(eggnog.subprocess, "run", fake_run)

    assert eggnog._tool_version("emapper.py") == "emapper-2.1.15"
