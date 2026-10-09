from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

from dualrag.config import SequenceConfig
from dualrag.models import ProteinQuery, SequenceEvidence
from dualrag.parsing import optional_float, terms


def retrieve(
    queries: list[ProteinQuery],
    input_path: Path,
    raw_dir: Path,
    config: SequenceConfig,
) -> tuple[list[SequenceEvidence], list[str]]:
    """Run eggNOG-mapper and parse its documented annotation table."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    prefix = "sequence"
    command = [
        config.executable,
        "-i",
        str(input_path),
        "--itype",
        "proteins",
        "--data_dir",
        str(config.eggnog_data_dir),
        "--output",
        prefix,
        "--output_dir",
        str(raw_dir),
        "--cpu",
        str(config.cpu),
        "--override",
        "-m",
        config.search_mode,
    ]
    if config.search_mode == "mmseqs" and config.mmseqs_db is not None:
        command.extend(["--mmseqs_db", str(config.mmseqs_db)])
    command.extend(config.extra_args)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    (raw_dir / "eggnog.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (raw_dir / "eggnog.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"eggNOG-mapper failed with exit code {completed.returncode}; "
            f"see {raw_dir / 'eggnog.stderr.txt'}"
        )

    annotation_path = raw_dir / f"{prefix}.emapper.annotations"
    if not annotation_path.is_file():
        raise RuntimeError(f"eggNOG-mapper did not create {annotation_path}")
    hits = parse_annotations(annotation_path, queries, config)
    return hits, command


def parse_annotations(
    path: Path, queries: list[ProteinQuery], config: SequenceConfig
) -> list[SequenceEvidence]:
    header: list[str] | None = None
    data_lines: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line.startswith("##") or not line:
                continue
            if line.startswith("#"):
                candidate = line.lstrip("#").split("\t")
                if "query" in candidate:
                    header = candidate
                continue
            data_lines.append(line)
    if header is None:
        raise ValueError(f"eggNOG annotation table has no #query header: {path}")

    query_ids = {query.query_id for query in queries}
    grouped: dict[str, list[SequenceEvidence]] = {query.query_id: [] for query in queries}
    tool_version = _tool_version(config.executable)
    for row in csv.DictReader(data_lines, fieldnames=header, delimiter="\t"):
        query_id = row.get("query", "")
        if query_id not in query_ids:
            continue
        seed = _none(row.get("seed_ortholog")) or "unresolved"
        hit = SequenceEvidence(
            query_id=query_id,
            target_id=seed,
            tool="eggNOG-mapper",
            tool_version=tool_version,
            database=config.database_name,
            database_version=config.database_version,
            evalue=optional_float(_none(row.get("evalue"))),
            bitscore=optional_float(_none(row.get("score"))),
            orthologous_group=_none(row.get("eggNOG_OGs")),
            protein_name=_none(row.get("Description")),
            go_terms=_split(row.get("GOs")),
            ec_numbers=_split(row.get("EC")),
            kegg_terms=_kegg_terms(row),
            pfam_ids=_split(row.get("PFAMs")),
            raw_output_path=str(path),
            source_accession=seed,
        )
        grouped[query_id].append(hit)
    return [hit for query in queries for hit in grouped[query.query_id][: config.top_k]]


def _split(value: str | None) -> list[str]:
    return terms((value or "").replace(",", ";") if value not in {None, "-"} else "")


def _kegg_terms(row: dict[str, str]) -> list[str]:
    values: list[str] = []
    for key in ("KEGG_ko", "KEGG_Pathway", "KEGG_Module", "KEGG_Reaction"):
        values.extend(_split(row.get(key)))
    return sorted(set(values))


def _none(value: str | None) -> str | None:
    return None if value in {None, "", "-"} else value


def _tool_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=False, timeout=30
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r"emapper-[^\s/]+", output)
    return match.group(0) if match else "unknown"
