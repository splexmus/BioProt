from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "download_phase1_full_data.sh"


def test_full_data_downloader_dry_run_has_no_network_transfer(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--data-root",
            str(tmp_path),
            "--components",
            "sifts,swissprot,eggnog-extras,uniref90",
            "--minimum-free-gb",
            "0",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "mode: dry run" in completed.stdout
    assert "pdb_chain_uniprot.tsv.gz" in completed.stdout
    assert "uniprot_sprot.fasta.gz" in completed.stdout
    assert "mmseqs.tar.gz" in completed.stdout
    assert "uniref90.fasta.gz" in completed.stdout
    assert not list(tmp_path.rglob("*.part"))


def test_full_data_downloader_requires_confirmation(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--data-root",
            str(tmp_path),
            "--components",
            "sifts",
            "--minimum-free-gb",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "pass --yes after reviewing --dry-run output" in completed.stderr
