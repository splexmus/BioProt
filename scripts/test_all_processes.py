"""Cross-platform safe offline engineering test (Windows-friendly).

Mirrors scripts/test_all_processes.sh step for step, but runs on any OS with only
Python. It uses no network, no HDD paths, no Ollama, no large biological databases,
and never reads sealed test labels. The Bash runner checks are executed only when a
POSIX bash is available, so on Windows they are reported as skipped.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dualrag.tools import posix_bash

ROOT = Path(__file__).resolve().parents[1]
STEPS = 7


def step(number: int, title: str) -> None:
    print(f"\n[{number}/{STEPS}] {title}", flush=True)


def run(*args: str | Path) -> None:
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


def main() -> int:
    if not (ROOT / "pixi.toml").is_file() or not (ROOT / "config" / "config.yaml").is_file():
        print("Run this script from the BioProt repository.", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="dualrag-all-processes-") as temp:
        work = Path(temp)

        step(1, "Unit tests")
        run("-m", "pytest", "-q")

        step(2, "Formatting and static checks")
        # conda-forge ships ruff as an executable, not an importable module.
        ruff = shutil.which("ruff")
        if ruff is None:
            print("ruff is required: run this through `pixi run`.", file=sys.stderr)
            return 1
        subprocess.run(
            [ruff, "check", "src", "tests", "scripts/test_all_processes.py"], cwd=ROOT, check=True
        )

        step(3, "CLI and external-tool diagnostics")
        subprocess.run(
            [sys.executable, "-m", "dualrag", "--help"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        run("-m", "dualrag", "check-tools")

        step(4, "User interface and offline Phase 1-2 fixture")
        for name in ("first", "second"):
            run(
                "-m", "dualrag", "analyze",
                "--config", "config/config.yaml",
                "--fasta", "tests/fixtures/queries.fasta",
                "--output", work / name,
            )  # fmt: skip

        step(5, "Reproducibility comparison")
        run(
            "-m", "dualrag", "compare-runs",
            "--first", work / "first" / "biological",
            "--second", work / "second" / "biological",
            "--output", work / "reproducibility.json",
        )  # fmt: skip

        step(6, "Phase 4 leakage-safe query construction")
        run(
            "-m", "dualrag", "build-literature-queries",
            "--run", work / "first" / "biological",
            "--output", work / "literature-queries",
            "--context", "tests/fixtures/literature_query_context.tsv",
        )  # fmt: skip

        step(7, "Phase runner interfaces")
        bash = posix_bash()
        runners = ("run_phase4_on_hdd.sh", "run_phase5_ollama.sh", "run_phase6_calibration.sh")
        if bash is None:
            runner_status = "SKIP  Phase 4-6 Bash runners (no POSIX bash; use Linux or WSL2)"
            print(runner_status)
        else:
            for runner in runners:
                subprocess.run([bash, "-n", f"scripts/{runner}"], cwd=ROOT, check=True)
            runner_status = "PASS  Phase 4-6 runner syntax"

    print(
        f"""
SAFE OFFLINE TEST: PASS

Covered:
  PASS  Python unit and contract tests, including the literature vector index
  PASS  Ruff static checks
  PASS  CLI loading and tool diagnostics
  PASS  FASTA user interface, status, input manifest, and summary
  PASS  Phase 1 sequence/structure fixture retrieval
  PASS  Phase 2 normalization, fusion, conflict, and audit outputs
  PASS  Repeat-run reproducibility
  PASS  Phase 4 query construction
  {runner_status}

Not executed automatically:
  MANUAL  Real eggNOG/MMseqs2, AlphaFold API, and Foldseek database search (Linux/WSL2)
  MANUAL  Phase 3 scientific benchmark or any sealed test labels
  MANUAL  PubMed/PMC network acquisition and human literature labels
  MANUAL  Ollama Phase 5 report generation and expert review
  MANUAL  Phase 6 calibration or frozen validation

See docs/TESTING_ALL_PROCESSES.md for the manual commands and interpretation rules."""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
