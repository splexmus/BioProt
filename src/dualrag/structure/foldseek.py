from __future__ import annotations

import csv
import re
import shutil
import subprocess
from pathlib import Path

from dualrag.config import StructureConfig
from dualrag.models import ProteinQuery, StructureEvidence
from dualrag.parsing import optional_float, optional_int, terms

FORMAT_FIELDS = [
    "query", "target", "evalue", "bits", "alntmscore", "alnlen", "qcov", "tcov", "fident"
]


def retrieve(
    queries: list[ProteinQuery],
    models: dict[str, Path],
    raw_dir: Path,
    tmp_dir: Path,
    config: StructureConfig,
) -> tuple[list[StructureEvidence], list[str] | None]:
    if not models:
        return [], None
    query_dir = raw_dir / "foldseek_queries"
    query_dir.mkdir(parents=True, exist_ok=True)
    safe_to_query: dict[str, str] = {}
    for index, query in enumerate(queries):
        model = models.get(query.query_id)
        if model is None:
            continue
        safe_id = f"q{index:06d}"
        safe_to_query[safe_id] = query.query_id
        shutil.copyfile(model, query_dir / f"{safe_id}{model.suffix}")
    output_path = raw_dir / "foldseek_hits.tsv"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    command = [
        config.executable, "easy-search", str(query_dir), str(config.foldseek_db),
        str(output_path), str(tmp_dir), "--format-output", ",".join(FORMAT_FIELDS),
        "--threads", str(config.threads), "--max-seqs", str(config.top_k),
        "-s", str(config.sensitivity),
    ]
    command.extend(config.extra_args)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    (raw_dir / "foldseek.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (raw_dir / "foldseek.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Foldseek failed with exit code {completed.returncode}; "
            f"see {raw_dir / 'foldseek.stderr.txt'}"
        )
    return parse_results(output_path, safe_to_query, config), command


def parse_results(
    path: Path, safe_to_query: dict[str, str], config: StructureConfig
) -> list[StructureEvidence]:
    selected: list[tuple[str, dict[str, str]]] = []
    counts: dict[str, int] = {}
    if not path.is_file():
        raise RuntimeError(f"Foldseek did not create {path}")
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            values = line.rstrip("\n").split("\t")
            if len(values) != len(FORMAT_FIELDS):
                raise ValueError(f"unexpected Foldseek column count in {path}: {len(values)}")
            row = dict(zip(FORMAT_FIELDS, values, strict=True))
            safe_id = Path(row["query"]).stem.split("_")[0]
            query_id = safe_to_query.get(safe_id)
            if query_id is None or counts.get(query_id, 0) >= config.top_k:
                continue
            counts[query_id] = counts.get(query_id, 0) + 1
            selected.append((query_id, row))

    metadata = _metadata(config.target_metadata, {row["target"] for _, row in selected})
    version = _tool_version(config.executable)
    hits: list[StructureEvidence] = []
    for query_id, row in selected:
        target = row["target"]
        target_meta = metadata.get(target, {})
        hits.append(
            StructureEvidence(
                query_id=query_id,
                target_structure_id=target,
                target_uniprot_id=target_meta.get("target_uniprot_id") or None,
                tool="Foldseek",
                tool_version=version,
                database=config.database_name,
                database_version=config.database_version,
                foldseek_evalue=optional_float(row["evalue"]),
                foldseek_score=optional_float(row["bits"]),
                tm_score=optional_float(row["alntmscore"]),
                alignment_length=optional_int(row["alnlen"]),
                query_coverage=optional_float(row["qcov"]),
                target_coverage=optional_float(row["tcov"]),
                sequence_identity=optional_float(row["fident"]),
                protein_name=target_meta.get("protein_name") or None,
                interpro_ids=terms(target_meta.get("interpro_ids")),
                supfam_ids=terms(target_meta.get("supfam_ids")),
                structure_source=target_meta.get("structure_source") or config.database_name,
                experimental_structure=_bool_or_none(
                    target_meta.get("experimental_structure")
                ),
                raw_output_path=str(path),
                source_accession=target_meta.get("source_accession") or target,
            )
        )
    return hits


def _metadata(
    path: Path | None, selected_targets: set[str]
) -> dict[str, dict[str, str]]:
    if path is None or not selected_targets:
        return {}
    metadata: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        if not rows.fieldnames or "target_structure_id" not in rows.fieldnames:
            raise ValueError("Foldseek target metadata requires target_structure_id")
        for row in rows:
            target = row["target_structure_id"]
            if target in selected_targets:
                metadata[target] = row
                if len(metadata) == len(selected_targets):
                    break
    return metadata


def _bool_or_none(value: str | None) -> bool | None:
    if not value:
        return None
    if value.casefold() not in {"true", "false"}:
        raise ValueError(f"expected true/false in target metadata, got {value!r}")
    return value.casefold() == "true"


def _tool_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "version"], capture_output=True, text=True, check=False, timeout=30
    )
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    match = re.search(r"[0-9]+\.[A-Za-z0-9.]+", output)
    return match.group(0) if match else "unknown"
