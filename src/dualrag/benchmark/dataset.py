from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STANDARD_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
EXPERIMENTAL_GO_CODES = frozenset(
    {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "HTP", "HDA", "HMP", "HGI", "HEP"}
)
EC_RE = re.compile(r"EC=(\d+\.\d+\.\d+\.\d+)\s+\{([^}]*)\}")
PMID_RE = re.compile(r"PubMed:(\d+)")
FULL_NAME_RE = re.compile(r"Full=([^;{]+)")


@dataclass(frozen=True)
class GoldLabel:
    namespace: str
    identifier: str
    evidence_tier: str
    evidence_code: str
    supporting_reference: str
    admissible_for_primary: bool
    decision_reason: str


@dataclass
class SwissProtEntry:
    accession: str = ""
    entry_name: str = ""
    protein_name: str = ""
    organism: str = ""
    taxonomy_id: str = ""
    superkingdom: str = "Other"
    protein_existence: str = ""
    entry_version: str = ""
    fragment: bool = False
    sequence: str = ""
    labels: list[GoldLabel] = field(default_factory=list)
    interpro_ids: list[str] = field(default_factory=list)
    pfam_ids: list[str] = field(default_factory=list)

    @property
    def sequence_sha256(self) -> str:
        return hashlib.sha256(self.sequence.encode("ascii")).hexdigest()

    @property
    def fasta_id(self) -> str:
        return f"sp|{self.accession}|{self.entry_name}"


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def parse_swissprot(path: Path) -> Iterator[SwissProtEntry]:
    """Stream canonical records from a UniProtKB/Swiss-Prot flat file."""
    fields: dict[str, list[str]] = defaultdict(list)
    sequence_lines: list[str] = []
    in_sequence = False
    with _open_text(path) as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line == "//":
                if fields:
                    yield _entry_from_fields(fields, "".join(sequence_lines))
                fields = defaultdict(list)
                sequence_lines = []
                in_sequence = False
                continue
            if in_sequence:
                sequence_lines.append("".join(line.split()))
                continue
            key = line[:2]
            value = line[5:] if len(line) >= 5 else ""
            fields[key].append(value)
            if key == "SQ":
                in_sequence = True


def _entry_from_fields(fields: dict[str, list[str]], sequence: str) -> SwissProtEntry:
    id_parts = fields["ID"][0].split()
    accession = fields["AC"][0].split(";")[0].strip()
    organism = " ".join(fields["OS"]).rstrip(".")
    taxonomy_match = re.search(r"NCBI_TaxID=(\d+)", " ".join(fields["OX"]))
    pe = fields["PE"][0].split(":", maxsplit=1)[0].strip() if fields["PE"] else ""
    oc_first = fields["OC"][0].split(";", maxsplit=1)[0].strip() if fields["OC"] else "Other"
    known_superkingdoms = {"Eukaryota", "Bacteria", "Archaea", "Viruses"}
    superkingdom = oc_first if oc_first in known_superkingdoms else "Other"
    description = " ".join(fields["DE"])
    name_match = FULL_NAME_RE.search(description)
    entry_version_match = re.search(r"entry version (\d+)", " ".join(fields["DT"]))
    labels: list[GoldLabel] = []

    for identifier, evidence in EC_RE.findall(description):
        pmids = PMID_RE.findall(evidence)
        is_experimental = "ECO:0000269" in evidence and bool(pmids)
        labels.append(
            GoldLabel(
                namespace="EC",
                identifier=identifier,
                evidence_tier="A" if is_experimental else "B",
                evidence_code="ECO:0000269" if "ECO:0000269" in evidence else evidence,
                supporting_reference=";".join(f"PMID:{pmid}" for pmid in pmids),
                admissible_for_primary=is_experimental,
                decision_reason=(
                    "full EC with experimental UniProt evidence and PubMed reference"
                    if is_experimental
                    else "not a full experimentally referenced EC assignment"
                ),
            )
        )

    interpro_ids: list[str] = []
    pfam_ids: list[str] = []
    for row in fields["DR"]:
        parts = [part.strip() for part in row.split(";")]
        if len(parts) < 2:
            continue
        if parts[0] == "GO" and len(parts) >= 4 and parts[2].startswith("F:"):
            code, _, source = parts[3].partition(":")
            experimental = code in EXPERIMENTAL_GO_CODES
            labels.append(
                GoldLabel(
                    namespace="GO_MF",
                    identifier=parts[1],
                    evidence_tier="A" if experimental else "B",
                    evidence_code=code,
                    supporting_reference=(
                        f"annotation-source:{source.rstrip('.')}" if source else ""
                    ),
                    admissible_for_primary=experimental and parts[1] != "GO:0003674",
                    decision_reason=(
                        "experimental GO Molecular Function annotation in frozen Swiss-Prot record"
                        if experimental
                        else "GO evidence code is not accepted for Tier A"
                    ),
                )
            )
        elif parts[0] == "InterPro":
            interpro_ids.append(parts[1])
        elif parts[0] == "Pfam":
            pfam_ids.append(parts[1])

    return SwissProtEntry(
        accession=accession,
        entry_name=id_parts[0],
        protein_name=name_match.group(1).strip() if name_match else id_parts[0],
        organism=organism,
        taxonomy_id=taxonomy_match.group(1) if taxonomy_match else "",
        superkingdom=superkingdom,
        protein_existence=pe,
        entry_version=entry_version_match.group(1) if entry_version_match else "",
        fragment="Fragment" in description,
        sequence=sequence,
        labels=labels,
        interpro_ids=sorted(set(interpro_ids)),
        pfam_ids=sorted(set(pfam_ids)),
    )


def is_eligible(entry: SwissProtEntry, minimum_length: int, maximum_length: int) -> bool:
    return (
        entry.protein_existence == "1"
        and not entry.fragment
        and minimum_length <= len(entry.sequence) <= maximum_length
        and bool(entry.sequence)
        and set(entry.sequence) <= STANDARD_AMINO_ACIDS
        and any(label.admissible_for_primary for label in entry.labels)
    )


def select_balanced_entries(
    candidates: Iterable[SwissProtEntry], size: int, seed: int
) -> list[SwissProtEntry]:
    """Select deterministically while spreading queries across superkingdoms."""
    by_group: dict[str, list[SwissProtEntry]] = defaultdict(list)
    for entry in candidates:
        by_group[entry.superkingdom].append(entry)
    rng = random.Random(seed)
    for values in by_group.values():
        values.sort(key=lambda entry: entry.accession)
        rng.shuffle(values)

    ordered_groups = ("Eukaryota", "Bacteria", "Archaea", "Viruses", "Other")
    groups = [group for group in ordered_groups if by_group[group]]
    selected: list[SwissProtEntry] = []
    while len(selected) < size:
        added = False
        for group in groups:
            if by_group[group] and len(selected) < size:
                selected.append(by_group[group].pop())
                added = True
        if not added:
            break
    return sorted(selected, key=lambda entry: entry.accession)


def _write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _run(command: list[str], log: list[str]) -> None:
    log.append(" ".join(command))
    subprocess.run(command, check=True)


def _read_cluster_tsv(path: Path) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for representative, member in csv.reader(handle, delimiter="\t"):
            clusters[representative].append(member)
    return dict(clusters)


def assign_cluster_splits(
    clusters: dict[str, list[str]], seed: int, ratios: dict[str, float]
) -> dict[str, str]:
    """Assign intact clusters, greedily minimizing query-count ratio error."""
    total = sum(len(members) for members in clusters.values())
    targets = {name: total * ratio for name, ratio in ratios.items()}
    counts = dict.fromkeys(ratios, 0)
    items = list(clusters.items())
    random.Random(seed).shuffle(items)
    items.sort(key=lambda item: len(item[1]), reverse=True)
    assignment: dict[str, str] = {}
    for representative, members in items:
        split = min(ratios, key=lambda name: (counts[name] + len(members)) / max(targets[name], 1))
        counts[split] += len(members)
        assignment[representative] = split
    return assignment


def _parse_accession(identifier: str) -> str:
    parts = identifier.split("|")
    return parts[1] if len(parts) >= 3 else identifier.split()[0]


def build_leakage_outputs(
    alignments_path: Path,
    entries: list[SwissProtEntry],
    target_checksums: dict[str, str],
    output_dir: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    query_by_id = {entry.fasta_id: entry for entry in entries}
    query_by_id.update({entry.accession: entry for entry in entries})
    prohibited: list[dict[str, object]] = []
    allowed: dict[str, list[dict[str, object]]] = defaultdict(list)
    alignment_fields = ["query", "target", "fident", "qcov", "tcov", "evalue", "bits"]
    with alignments_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle, fieldnames=alignment_fields, delimiter="\t")
        for row in reader:
            if row["query"] == "query":
                continue
            query = query_by_id.get(row["query"])
            if query is None:
                query_accession = _parse_accession(row["query"])
                query = next((e for e in entries if e.accession == query_accession), None)
            if query is None:
                raise ValueError(f"unknown query identifier in alignment table: {row['query']}")
            target_accession = _parse_accession(row["target"])
            identity = float(row["fident"])
            qcov = float(row["qcov"])
            tcov = float(row["tcov"])
            reason = ""
            if target_accession == query.accession:
                reason = "EXACT_ACCESSION"
            elif target_checksums.get(target_accession) == query.sequence_sha256:
                reason = "IDENTICAL_SEQUENCE_SHA256"
            elif identity >= 0.90 and qcov >= 0.80 and tcov >= 0.80:
                reason = "PROHIBITED_CLOSE_HOMOLOG"
            if reason:
                prohibited.append(
                    {
                        "query_accession": query.accession,
                        "target_identifier": target_accession,
                        "target_modality": "REFERENCE_SEQUENCE",
                        "exclusion_reason": reason,
                        "sequence_identity": f"{identity:.6f}",
                        "query_coverage": f"{qcov:.6f}",
                        "target_coverage": f"{tcov:.6f}",
                        "resolution_source": "UniProtKB/Swiss-Prot accession",
                    }
                )
            elif qcov >= 0.70 and tcov >= 0.70:
                allowed[query.accession].append(
                    {"target": target_accession, "identity": identity, "qcov": qcov, "tcov": tcov}
                )

    bins = [
        ("GT_70", lambda value: value > 0.70),
        ("FROM_50_TO_70", lambda value: 0.50 < value <= 0.70),
        ("FROM_30_TO_50", lambda value: 0.30 < value <= 0.50),
        ("FROM_20_TO_30", lambda value: 0.20 < value <= 0.30),
        ("LT_OR_EQ_20", lambda value: value <= 0.20),
    ]
    difficulty: list[dict[str, object]] = []
    for entry in entries:
        hits = sorted(
            allowed[entry.accession],
            key=lambda row: (-float(row["identity"]), str(row["target"])),
        )
        if hits:
            best = hits[0]
            stratum = next(name for name, predicate in bins if predicate(float(best["identity"])))
            difficulty.append(
                {
                    "accession": entry.accession,
                    "difficulty_stratum": stratum,
                    "closest_allowed_reference": best["target"],
                    "sequence_identity": f"{float(best['identity']):.6f}",
                    "query_coverage": f"{float(best['qcov']):.6f}",
                    "target_coverage": f"{float(best['tcov']):.6f}",
                    "reference_catalog": "UniProtKB/Swiss-Prot",
                }
            )
        else:
            difficulty.append(
                {
                    "accession": entry.accession,
                    "difficulty_stratum": "NO_ALLOWED_HIT",
                    "closest_allowed_reference": "",
                    "sequence_identity": "",
                    "query_coverage": "",
                    "target_coverage": "",
                    "reference_catalog": "UniProtKB/Swiss-Prot",
                }
            )
    return prohibited, difficulty


def build_benchmark_dataset(
    *,
    swissprot_dat: Path,
    swissprot_fasta: Path,
    contract_path: Path,
    output_dir: Path,
    dataset_id: str,
    source_release: str,
    source_sha256: str,
    size: int,
    mmseqs_executable: str = "mmseqs",
    resume: bool = False,
) -> dict[str, object]:
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    actual_source_sha256 = _sha256_file(swissprot_dat)
    if actual_source_sha256 != source_sha256:
        raise ValueError(
            "Swiss-Prot flat-file checksum mismatch: "
            f"expected {source_sha256}, observed {actual_source_sha256}"
        )
    minimum_length = int(contract["gold_standard"]["inclusion"]["minimum_length"])
    maximum_length = int(contract["gold_standard"]["inclusion"]["maximum_length"])
    seed = int(contract["random_seed"])
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[SwissProtEntry] = []
    target_checksums: dict[str, str] = {}
    for entry in parse_swissprot(swissprot_dat):
        target_checksums[entry.accession] = entry.sequence_sha256
        if is_eligible(entry, minimum_length, maximum_length):
            candidates.append(entry)
    entries = select_balanced_entries(candidates, size, seed)
    if len(entries) != size:
        raise ValueError(f"requested {size} entries but only {len(entries)} were eligible")

    queries_fasta = output_dir / "queries.fasta"
    with queries_fasta.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(f">{entry.fasta_id} {entry.protein_name}\n")
            for start in range(0, len(entry.sequence), 80):
                handle.write(entry.sequence[start : start + 80] + "\n")

    _write_tsv(
        output_dir / "queries.tsv",
        [
            "accession", "fasta_id", "canonical_sequence", "sequence_sha256", "sequence_length",
            "protein_name", "organism", "taxonomy_id", "taxonomy_superkingdom",
            "protein_existence", "source_database", "source_release", "entry_version",
            "inclusion_status", "inclusion_or_exclusion_reason",
        ],
        (
            {
                "accession": entry.accession,
                "fasta_id": entry.fasta_id,
                "canonical_sequence": entry.sequence,
                "sequence_sha256": entry.sequence_sha256,
                "sequence_length": len(entry.sequence),
                "protein_name": entry.protein_name,
                "organism": entry.organism,
                "taxonomy_id": entry.taxonomy_id,
                "taxonomy_superkingdom": entry.superkingdom,
                "protein_existence": "evidence_at_protein_level",
                "source_database": "UniProtKB/Swiss-Prot",
                "source_release": source_release,
                "entry_version": entry.entry_version,
                "inclusion_status": "INCLUDED",
                "inclusion_or_exclusion_reason": (
                    "meets phase3-benchmark-v1 Tier A and sequence rules"
                ),
            }
            for entry in entries
        ),
    )
    _write_tsv(
        output_dir / "gold_labels.tsv",
        [
            "accession", "namespace", "identifier", "evidence_tier", "evidence_code",
            "supporting_reference", "source_database", "source_release",
            "admissible_for_primary", "decision_reason",
        ],
        (
            {
                "accession": entry.accession,
                "namespace": label.namespace,
                "identifier": label.identifier,
                "evidence_tier": label.evidence_tier,
                "evidence_code": label.evidence_code,
                "supporting_reference": label.supporting_reference,
                "source_database": "UniProtKB/Swiss-Prot",
                "source_release": source_release,
                "admissible_for_primary": str(label.admissible_for_primary).lower(),
                "decision_reason": label.decision_reason,
            }
            for entry in entries
            for label in entry.labels
        ),
    )
    _write_tsv(
        output_dir / "domain_labels.tsv",
        ["accession", "namespace", "identifier", "source_database", "source_release", "use"],
        (
            {
                "accession": entry.accession,
                "namespace": namespace,
                "identifier": identifier,
                "source_database": "UniProtKB/Swiss-Prot cross-reference",
                "source_release": source_release,
                "use": "secondary_consistency_only",
            }
            for entry in entries
            for namespace, identifiers in (
                ("INTERPRO", entry.interpro_ids),
                ("PFAM", entry.pfam_ids),
            )
            for identifier in identifiers
        ),
    )

    command_log: list[str] = []
    cluster_prefix = output_dir / "mmseqs-clusters"
    cluster_tmp = output_dir / "tmp-cluster"
    cluster_tsv = Path(f"{cluster_prefix}_cluster.tsv")
    cluster_command = [
        mmseqs_executable,
        "easy-cluster",
        str(queries_fasta),
        str(cluster_prefix),
        str(cluster_tmp),
        "--min-seq-id",
        "0.30",
        "-c",
        "0.80",
        "--cov-mode",
        "0",
        "--single-step-clustering",
        "1",
        "--threads",
        "1",
    ]
    if resume and cluster_tsv.exists():
        command_log.append(
            f"REUSED existing {cluster_tsv}; original command: {' '.join(cluster_command)}"
        )
    else:
        _run(cluster_command, command_log)
    clusters = _read_cluster_tsv(cluster_tsv)
    ratios = {"development": 0.70, "validation": 0.15, "test": 0.15}
    assignment = assign_cluster_splits(clusters, seed, ratios)
    membership_rows: list[dict[str, object]] = []
    split_by_accession: dict[str, str] = {}
    for representative, members in sorted(clusters.items()):
        split = assignment[representative]
        for member in sorted(members):
            accession = _parse_accession(member)
            split_by_accession[accession] = split
            membership_rows.append(
                {
                    "cluster_representative": _parse_accession(representative),
                    "accession": accession,
                    "split": split,
                    "minimum_identity": "0.30",
                    "minimum_query_coverage": "0.80",
                    "minimum_target_coverage": "0.80",
                    "seed": seed,
                }
            )
    _write_tsv(
        output_dir / "cluster_membership.tsv",
        [
            "cluster_representative", "accession", "split", "minimum_identity",
            "minimum_query_coverage", "minimum_target_coverage", "seed",
        ],
        membership_rows,
    )
    _write_tsv(
        output_dir / "splits.tsv",
        ["accession", "split", "cluster_representative"],
        (
            {
                "accession": row["accession"],
                "split": row["split"],
                "cluster_representative": row["cluster_representative"],
            }
            for row in sorted(membership_rows, key=lambda row: str(row["accession"]))
        ),
    )

    alignments_path = output_dir / "reference_alignments.tsv"
    search_tmp = output_dir / "tmp-search"
    search_command = [
        mmseqs_executable,
        "easy-search",
        str(queries_fasta),
        str(swissprot_fasta),
        str(alignments_path),
        str(search_tmp),
        "--format-output",
        "query,target,fident,qcov,tcov,evalue,bits",
        "--max-seqs",
        "1000",
        "-s",
        "7.5",
        "--cov-mode",
        "0",
        "-c",
        "0.70",
        "--threads",
        "1",
    ]
    if resume and alignments_path.exists():
        command_log.append(
            f"REUSED existing {alignments_path}; original command: {' '.join(search_command)}"
        )
    else:
        _run(search_command, command_log)
    prohibited, difficulty = build_leakage_outputs(
        alignments_path, entries, target_checksums, output_dir
    )
    _write_tsv(
        output_dir / "prohibited_targets.tsv",
        [
            "query_accession", "target_identifier", "target_modality", "exclusion_reason",
            "sequence_identity", "query_coverage", "target_coverage", "resolution_source",
        ],
        sorted(
            prohibited,
            key=lambda row: (str(row["query_accession"]), str(row["target_identifier"])),
        ),
    )
    _write_tsv(
        output_dir / "difficulty_strata.tsv",
        [
            "accession", "difficulty_stratum", "closest_allowed_reference", "sequence_identity",
            "query_coverage", "target_coverage", "reference_catalog",
        ],
        difficulty,
    )
    (output_dir / "commands.log").write_text("\n".join(command_log) + "\n", encoding="utf-8")

    split_counts = Counter(split_by_accession.values())
    difficulty_counts = Counter(str(row["difficulty_stratum"]) for row in difficulty)
    namespace_counts = Counter(
        label.namespace
        for entry in entries
        for label in entry.labels
        if label.admissible_for_primary
    )
    summary: dict[str, object] = {
        "dataset_id": dataset_id,
        "contract_id": contract["contract_id"],
        "source_database": "UniProtKB/Swiss-Prot",
        "source_release": source_release,
        "source_flat_file_sha256": source_sha256,
        "query_count": len(entries),
        "eligible_candidate_count": len(candidates),
        "taxonomy_counts": dict(sorted(Counter(entry.superkingdom for entry in entries).items())),
        "primary_label_counts": dict(sorted(namespace_counts.items())),
        "cluster_count": len(clusters),
        "split_query_counts": dict(sorted(split_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "prohibited_pair_count": len(prohibited),
        "limitations": [
            "This is a development pilot, not a statistically powered final benchmark.",
            "Reference difficulty uses Swiss-Prot, not the eggNOG or PDB target universe.",
            "Structure-target SIFTS exclusions must be materialized when Phase 3.6 retrieval runs.",
            "GO flat-file evidence preserves its source but not a direct publication identifier.",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_manifest = {
        "dataset_id": dataset_id,
        "contract": {"path": str(contract_path), "sha256": _sha256_file(contract_path)},
        "source": {
            "database": "UniProtKB/Swiss-Prot",
            "release": source_release,
            "flat_file": str(swissprot_dat),
            "flat_file_sha256": source_sha256,
            "fasta_file": str(swissprot_fasta),
            "fasta_file_sha256": _sha256_file(swissprot_fasta),
        },
        "selection": {
            "size": size,
            "seed": seed,
            "method": "round-robin superkingdom-balanced deterministic selection",
        },
        "mmseqs": {"version": _capture_version(mmseqs_executable), "commands_log": "commands.log"},
    }
    (output_dir / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_paths = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    checksum_lines = [f"{_sha256_file(path)}  {path.name}" for path in artifact_paths]
    (output_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return summary


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_version(executable: str) -> str:
    result = subprocess.run([executable, "version"], check=True, text=True, capture_output=True)
    return result.stdout.strip() or result.stderr.strip()
