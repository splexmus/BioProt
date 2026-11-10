from __future__ import annotations

import pytest

from dualrag.tools import posix_bash


@pytest.fixture
def bash() -> str:
    """A bash that understands host paths; skip where none exists (e.g. plain Windows)."""
    executable = posix_bash()
    if executable is None:
        pytest.skip("requires bash (Linux, WSL2, or Git for Windows)")
    return executable
