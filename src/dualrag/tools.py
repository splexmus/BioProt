from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolStatus:
    name: str
    executable: str
    available: bool
    version: str | None
    warning: str | None = None


TOOL_COMMANDS: dict[str, tuple[str, ...]] = {
    "MMseqs2": ("mmseqs", "version"),
    "eggNOG-mapper": ("emapper.py", "--version"),
    "Foldseek": ("foldseek", "version"),
    "HMMER": ("hmmsearch", "-h"),
    "BLAST+": ("blastp", "-version"),
    "DIAMOND": ("diamond", "version"),
}


def check_tools() -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for name, command in TOOL_COMMANDS.items():
        executable = command[0]
        resolved = shutil.which(executable)
        if resolved is None:
            statuses.append(ToolStatus(name, executable, False, None))
            continue
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            cwd=tempfile.gettempdir() if name == "eggNOG-mapper" else None,
        )
        combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        output = [
            re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            for line in combined.splitlines()
            if line.strip()
        ]
        if name == "eggNOG-mapper":
            version = next(
                (line for line in output if line.casefold().startswith("emapper-")), None
            )
        else:
            version = output[0] if output else None
        warning = None
        if any("error retrieving eggnog-mapper db data" in line.casefold() for line in output):
            warning = "executable found, but the eggNOG database is not configured"
        statuses.append(ToolStatus(name, resolved, completed.returncode == 0, version, warning))
    return statuses


def tool_status_dicts() -> list[dict[str, object]]:
    return [asdict(status) for status in check_tools()]


def posix_bash() -> str | None:
    """Return a bash that accepts this OS's paths, or None.

    On Windows, ``bash`` on PATH is often the WSL launcher in System32, which runs
    inside Linux and cannot open Windows drive paths. Prefer Git for Windows' bash.
    """
    candidate = shutil.which("bash")
    if os.name != "nt":
        return candidate
    if candidate and Path(candidate).parent.name.lower() not in {"system32", "windowsapps"}:
        return candidate
    git = shutil.which("git")
    if git:
        # <Git>\cmd\git.exe or <Git>\mingw64\bin\git.exe -> <Git>\bin\bash.exe
        for root in Path(git).resolve().parents:
            bundled = root / "bin" / "bash.exe"
            if bundled.is_file():
                return str(bundled)
    return None
