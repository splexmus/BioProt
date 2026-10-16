from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

HEADER = [
    "target_structure_id",
    "target_uniprot_id",
    "protein_name",
    "interpro_ids",
    "supfam_ids",
    "structure_source",
    "experimental_structure",
    "source_accession",
]
TARGET_PATTERN = re.compile(
    r"^(?P<pdb>[0-9A-Za-z]{4})-assembly[0-9]+_(?P<chain>.+)$"
)
COPY_SUFFIX_PATTERN = re.compile(r"^(?P<chain>.+)-[0-9]+$")


@dataclass(frozen=True)
class BuildResult:
    output: Path
    manifest: Path
    target_count: int
    uniprot_mapped_count: int
    protein_name_mapped_count: int
    interpro_mapped_count: int
    malformed_target_count: int
    duplicate_target_count: int


def build_metadata(
    *,
    foldseek_lookup: Path,
    sifts_uniprot: Path,
    sifts_interpro: Path,
    swissprot_fasta: Path,
    output: Path,
    work_dir: Path | None = None,
) -> BuildResult:
    """Build target metadata for a Foldseek PDB database from SIFTS and Swiss-Prot."""
    inputs = [foldseek_lookup, sifts_uniprot, sifts_interpro, swissprot_fasta]
    for path in inputs:
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"required non-empty input is missing: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    work_root = work_dir or output.parent
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="foldseek-metadata-", dir=work_root) as temp:
        database = Path(temp) / "metadata.sqlite3"
        connection = sqlite3.connect(database)
        try:
            _configure_database(connection)
            sifts_releases = {
                "pdb_chain_uniprot": _load_sifts(
                    connection,
                    sifts_uniprot,
                    expected_value_column="SP_PRIMARY",
                    table="uniprot_mapping",
                    value_column="accession",
                ),
                "pdb_chain_interpro": _load_sifts(
                    connection,
                    sifts_interpro,
                    expected_value_column="INTERPRO_ID",
                    table="interpro_mapping",
                    value_column="interpro_id",
                ),
            }
            _load_swissprot_names(connection, swissprot_fasta)
            malformed, duplicates = _load_foldseek_targets(connection, foldseek_lookup)
            _aggregate_chain_metadata(connection)
            result = _write_output(connection, output, malformed, duplicates)
        finally:
            connection.close()

    manifest = _write_manifest(
        result=result,
        inputs=inputs,
        sifts_releases=sifts_releases,
    )
    return BuildResult(**{**asdict(result), "manifest": manifest})


def _configure_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = FILE;
        CREATE TABLE uniprot_mapping (
            pdb TEXT NOT NULL,
            chain TEXT NOT NULL,
            accession TEXT NOT NULL,
            PRIMARY KEY (pdb, chain, accession)
        ) WITHOUT ROWID;
        CREATE TABLE interpro_mapping (
            pdb TEXT NOT NULL,
            chain TEXT NOT NULL,
            interpro_id TEXT NOT NULL,
            PRIMARY KEY (pdb, chain, interpro_id)
        ) WITHOUT ROWID;
        CREATE TABLE protein_name (
            accession TEXT PRIMARY KEY,
            name TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE foldseek_target (
            ordinal INTEGER PRIMARY KEY,
            target TEXT NOT NULL UNIQUE,
            pdb TEXT,
            chain_exact TEXT,
            chain_base TEXT
        );
        """
    )


def _prepend(first: str, remaining: Iterator[str]) -> Iterator[str]:
    yield first
    yield from remaining


def _load_sifts(
    connection: sqlite3.Connection,
    path: Path,
    *,
    expected_value_column: str,
    table: str,
    value_column: str,
) -> str:
    statement = (
        f"INSERT OR IGNORE INTO {table} (pdb, chain, {value_column}) VALUES (?, ?, ?)"
    )
    batch: list[tuple[str, str, str]] = []
    comments: list[str] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            if line.startswith("#"):
                comments.append(line[1:].strip())
                continue
            reader = csv.DictReader(_prepend(line, handle), delimiter="\t")
            required = {"PDB", "CHAIN", expected_value_column}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(f"{path} requires columns {sorted(required)}")
            for row in reader:
                pdb = row["PDB"].strip().lower()
                chain = row["CHAIN"].strip()
                value = row[expected_value_column].strip()
                if not pdb or not chain or not value:
                    continue
                batch.append((pdb, chain, value))
                if len(batch) >= 50_000:
                    connection.executemany(statement, batch)
                    batch.clear()
            break
        else:
            raise ValueError(f"no TSV header found in {path}")
    if batch:
        connection.executemany(statement, batch)
    connection.commit()
    return " | ".join(comments)


def _load_swissprot_names(connection: sqlite3.Connection, path: Path) -> None:
    statement = "INSERT OR REPLACE INTO protein_name (accession, name) VALUES (?, ?)"
    batch: list[tuple[str, str]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith(">"):
                continue
            accession, name = _parse_swissprot_header(line.rstrip("\n"))
            if accession and name:
                batch.append((accession, name))
            if len(batch) >= 50_000:
                connection.executemany(statement, batch)
                batch.clear()
    if batch:
        connection.executemany(statement, batch)
    connection.commit()


def _parse_swissprot_header(line: str) -> tuple[str, str]:
    match = re.match(r"^>sp\|([^|]+)\|\S+\s+(.+?)(?:\s+OS=|$)", line)
    if match is None:
        return "", ""
    return match.group(1), _clean_field(match.group(2))


def _load_foldseek_targets(connection: sqlite3.Connection, path: Path) -> tuple[int, int]:
    statement = (
        "INSERT OR IGNORE INTO foldseek_target "
        "(ordinal, target, pdb, chain_exact, chain_base) VALUES (?, ?, ?, ?, ?)"
    )
    batch: list[tuple[int, str, str | None, str | None, str | None]] = []
    malformed = 0
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            total += 1
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 2:
                raise ValueError(f"malformed Foldseek lookup row {line_number}: {line!r}")
            try:
                ordinal = int(fields[0])
            except ValueError as error:
                raise ValueError(
                    f"invalid Foldseek ordinal at row {line_number}: {fields[0]!r}"
                ) from error
            target = fields[1]
            match = TARGET_PATTERN.fullmatch(target)
            if match is None:
                malformed += 1
                row = (ordinal, target, None, None, None)
            else:
                chain = match.group("chain")
                copy_match = COPY_SUFFIX_PATTERN.fullmatch(chain)
                chain_base = copy_match.group("chain") if copy_match else chain
                row = (ordinal, target, match.group("pdb").lower(), chain, chain_base)
            batch.append(row)
            if len(batch) >= 50_000:
                connection.executemany(statement, batch)
                batch.clear()
    if batch:
        connection.executemany(statement, batch)
    connection.commit()
    unique = connection.execute("SELECT count(*) FROM foldseek_target").fetchone()[0]
    return malformed, total - unique


def _aggregate_chain_metadata(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE uniprot_agg AS
        SELECT pdb, chain, group_concat(accession, ';') AS accessions
        FROM (SELECT pdb, chain, accession FROM uniprot_mapping ORDER BY pdb, chain, accession)
        GROUP BY pdb, chain;
        CREATE UNIQUE INDEX uniprot_agg_key ON uniprot_agg (pdb, chain);

        CREATE TABLE name_agg AS
        SELECT pdb, chain, group_concat(name, ';') AS names
        FROM (
            SELECT DISTINCT mapping.pdb, mapping.chain, names.name
            FROM uniprot_mapping AS mapping
            JOIN protein_name AS names ON names.accession = mapping.accession
            ORDER BY mapping.pdb, mapping.chain, names.name
        )
        GROUP BY pdb, chain;
        CREATE UNIQUE INDEX name_agg_key ON name_agg (pdb, chain);

        CREATE TABLE interpro_agg AS
        SELECT pdb, chain, group_concat(interpro_id, ';') AS interpro_ids
        FROM (
            SELECT pdb, chain, interpro_id
            FROM interpro_mapping
            ORDER BY pdb, chain, interpro_id
        )
        GROUP BY pdb, chain;
        CREATE UNIQUE INDEX interpro_agg_key ON interpro_agg (pdb, chain);
        """
    )


def _write_output(
    connection: sqlite3.Connection, output: Path, malformed: int, duplicates: int
) -> BuildResult:
    temporary = output.with_name(f".{output.name}.tmp")
    counts = {"target": 0, "uniprot": 0, "name": 0, "interpro": 0}
    query = """
        SELECT
            targets.target,
            targets.pdb,
            COALESCE(uniprot_exact.accessions, uniprot_base.accessions, ''),
            COALESCE(name_exact.names, name_base.names, ''),
            COALESCE(interpro_exact.interpro_ids, interpro_base.interpro_ids, '')
        FROM foldseek_target AS targets
        LEFT JOIN uniprot_agg AS uniprot_exact
          ON uniprot_exact.pdb = targets.pdb AND uniprot_exact.chain = targets.chain_exact
        LEFT JOIN uniprot_agg AS uniprot_base
          ON uniprot_base.pdb = targets.pdb AND uniprot_base.chain = targets.chain_base
        LEFT JOIN name_agg AS name_exact
          ON name_exact.pdb = targets.pdb AND name_exact.chain = targets.chain_exact
        LEFT JOIN name_agg AS name_base
          ON name_base.pdb = targets.pdb AND name_base.chain = targets.chain_base
        LEFT JOIN interpro_agg AS interpro_exact
          ON interpro_exact.pdb = targets.pdb AND interpro_exact.chain = targets.chain_exact
        LEFT JOIN interpro_agg AS interpro_base
          ON interpro_base.pdb = targets.pdb AND interpro_base.chain = targets.chain_base
        ORDER BY targets.ordinal
    """
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(HEADER)
            for target, pdb, accessions, names, interpro_ids in connection.execute(query):
                writer.writerow(
                    [
                        target,
                        _clean_output_field(accessions),
                        _clean_output_field(names),
                        _clean_output_field(interpro_ids),
                        "",
                        "PDB",
                        "true",
                        pdb or "",
                    ]
                )
                counts["target"] += 1
                counts["uniprot"] += bool(accessions)
                counts["name"] += bool(names)
                counts["interpro"] += bool(interpro_ids)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    if counts["target"] == 0 or counts["uniprot"] == 0:
        raise RuntimeError("metadata build produced no targets or no UniProt mappings")
    return BuildResult(
        output=output,
        manifest=Path(),
        target_count=counts["target"],
        uniprot_mapped_count=counts["uniprot"],
        protein_name_mapped_count=counts["name"],
        interpro_mapped_count=counts["interpro"],
        malformed_target_count=malformed,
        duplicate_target_count=duplicates,
    )


def _clean_field(value: str) -> str:
    return " ".join(value.replace("\t", " ").replace(";", ",").split())


def _clean_output_field(value: str) -> str:
    return " ".join(value.replace("\t", " ").split())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(
    *,
    result: BuildResult,
    inputs: list[Path],
    sifts_releases: dict[str, str],
) -> Path:
    manifest = result.output.with_suffix(result.output.suffix + ".manifest.json")
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "output": str(result.output),
        "output_sha256": _sha256(result.output),
        "counts": {
            "targets": result.target_count,
            "targets_with_uniprot": result.uniprot_mapped_count,
            "targets_with_protein_name": result.protein_name_mapped_count,
            "targets_with_interpro": result.interpro_mapped_count,
            "malformed_target_ids": result.malformed_target_count,
            "duplicate_lookup_rows_collapsed": result.duplicate_target_count,
        },
        "inputs": [
            {"path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in inputs
        ],
        "source_release_headers": sifts_releases,
        "notes": [
            "Foldseek target IDs are preserved exactly from the lookup file.",
            "UniProt and InterPro mappings are chain-level SIFTS annotations.",
            "Protein names are available only for reviewed Swiss-Prot accessions.",
            "supfam_ids is blank because no SUPFAM mapping source was supplied.",
        ],
    }
    temporary = manifest.with_name(f".{manifest.name}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(manifest)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Foldseek PDB target metadata from SIFTS and Swiss-Prot."
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root: Path = args.data_root
    output = args.output or data_root / "databases/foldseek/pdb_metadata.tsv"
    try:
        result = build_metadata(
            foldseek_lookup=data_root / "databases/foldseek/pdb.lookup",
            sifts_uniprot=(
                data_root / "databases/metadata/sifts/pdb_chain_uniprot.tsv.gz"
            ),
            sifts_interpro=(
                data_root / "databases/metadata/sifts/pdb_chain_interpro.tsv.gz"
            ),
            swissprot_fasta=(
                data_root
                / "databases/uniprot/swissprot/current/uniprot_sprot.fasta.gz"
            ),
            output=output,
            work_dir=args.work_dir,
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {result.target_count:,} targets to {result.output}")
    print(
        f"mapped: UniProt {result.uniprot_mapped_count:,}; "
        f"names {result.protein_name_mapped_count:,}; "
        f"InterPro {result.interpro_mapped_count:,}"
    )
    print(f"provenance: {result.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
