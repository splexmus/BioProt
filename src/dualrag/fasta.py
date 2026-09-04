from __future__ import annotations

import re
from pathlib import Path

from dualrag.models import ProteinQuery

_AMINO_ACIDS = frozenset("ABCDEFGHIKLMNPQRSTVWXYZUO*-J")


def read_fasta(path: Path) -> list[ProteinQuery]:
    queries: list[ProteinQuery] = []
    current_header: str | None = None
    sequence_parts: list[str] = []
    seen: set[str] = set()

    def finish() -> None:
        if current_header is None:
            return
        identifier, _, description = current_header.partition(" ")
        sequence = "".join(sequence_parts).upper()
        if not sequence:
            raise ValueError(f"empty FASTA sequence for {identifier!r}")
        invalid = sorted(set(sequence) - _AMINO_ACIDS)
        if invalid:
            raise ValueError(f"invalid residue(s) for {identifier!r}: {''.join(invalid)}")
        if identifier in seen:
            raise ValueError(f"duplicate FASTA identifier: {identifier!r}")
        seen.add(identifier)
        queries.append(ProteinQuery(identifier, sequence, description or None))

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith(">"):
            finish()
            current_header = line[1:].strip()
            sequence_parts = []
            if not current_header:
                raise ValueError(f"empty FASTA header at line {line_number}")
        else:
            if current_header is None:
                raise ValueError(f"sequence before first FASTA header at line {line_number}")
            sequence_parts.append(re.sub(r"\s+", "", line))
    finish()
    if not queries:
        raise ValueError("FASTA file contains no records")
    return queries
