from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import asdict, dataclass


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
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
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
