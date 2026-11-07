from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from dualrag.benchmark.dataset import (
    STANDARD_AMINO_ACIDS,
    SwissProtEntry,
    _capture_version,
    _parse_accession,
    _read_cluster_tsv,
    _run,
    _sha256_file,
    _write_tsv,
    assign_cluster_splits,
    build_leakage_outputs,
    parse_swissprot,
)


@dataclass(frozen=True)
class Nomination:
    accession: str
    source_file: str
    supplied_reviewed_value: str
    accepted_as_reviewed: bool


def read_nomination_sources(paths: list[Path]) -> list[Nomination]:
    """Read UniProt exports; only the Reviewed column determines supplied review status."""
    nominations: list[Nomination] = []
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None or "Entry" not in reader.fieldnames:
                raise ValueError(f"nomination source lacks Entry column: {path}")
            if "Reviewed" not in reader.fieldnames:
                raise ValueError(f"nomination source lacks Reviewed column: {path}")
            seen: set[str] = set()
            for row in reader:
                accession = row["Entry"].strip()
                if not accession:
                    raise ValueError(f"blank Entry in nomination source: {path}")
                if accession in seen:
                    raise ValueError(f"duplicate accession {accession} in {path}")
                seen.add(accession)
                supplied = row["Reviewed"].strip()
                nominations.append(
                    Nomination(
                        accession=accession,
                        source_file=str(path),
                        supplied_reviewed_value=supplied,
                        accepted_as_reviewed=supplied.casefold() == "reviewed",
                    )
                )
    return nominations


def build_step3_merged_dataset(
    *,
    nomination_paths: list[Path],
    swissprot_dat: Path,
    swissprot_fasta: Path,
    pilot_queries: Path,
    external_panel: Path,
    contract_path: Path,
    output_dir: Path,
    dataset_id: str,
    source_release: str,
    source_sha256: str,
    mmseqs_executable: str = "mmseqs",
) -> dict[str, object]:
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if _sha256_file(swissprot_dat) != source_sha256:
        raise ValueError("Swiss-Prot flat-file checksum does not match declared release")
    nominations = read_nomination_sources(nomination_paths)
    by_accession: dict[str, list[Nomination]] = defaultdict(list)
    for nomination in nominations:
        by_accession[nomination.accession].append(nomination)
    reviewed_accessions = {
        accession
        for accession, values in by_accession.items()
        if any(value.accepted_as_reviewed for value in values)
    }
    exposed_accessions = _read_exposed_accessions(pilot_queries, external_panel)
    wanted = reviewed_accessions | exposed_accessions
    entries: dict[str, SwissProtEntry] = {}
    target_checksums: dict[str, str] = {}
    for entry in parse_swissprot(swissprot_dat):
        target_checksums[entry.accession] = entry.sequence_sha256
        if entry.accession in wanted:
            entries[entry.accession] = entry

    minimum_length = int(contract["gold_standard"]["inclusion"]["minimum_length"])
    maximum_length = int(contract["gold_standard"]["inclusion"]["maximum_length"])
    reasons: dict[str, list[str]] = {}
    preleakage: list[SwissProtEntry] = []
    for accession in sorted(reviewed_accessions):
        entry = entries.get(accession)
        current = _eligibility_reasons(entry, minimum_length, maximum_length)
        reasons[accession] = current
        if not current and entry is not None:
            preleakage.append(entry)

    output_dir.mkdir(parents=True, exist_ok=False)
    commands: list[str] = []
    overlap_fasta = output_dir / "exposed-candidate-overlap.fasta"
    with overlap_fasta.open("w", encoding="utf-8") as handle:
        for accession in sorted(exposed_accessions):
            entry = entries.get(accession)
            if entry is not None:
                handle.write(f">exposed::{accession}\n{entry.sequence}\n")
        for entry in preleakage:
            handle.write(f">candidate::{entry.accession}\n{entry.sequence}\n")
    overlap_prefix = output_dir / "exposed-candidate-clusters"
    overlap_command = _cluster_command(
        mmseqs_executable,
        overlap_fasta,
        overlap_prefix,
        output_dir / "tmp-exposed-clusters",
    )
    _run(overlap_command, commands)
    overlap_clusters = _read_cluster_tsv(Path(f"{overlap_prefix}_cluster.tsv"))
    exposed_cluster_candidates: set[str] = set()
    for members in overlap_clusters.values():
        has_exposed = any(member.startswith("exposed::") for member in members)
        if has_exposed:
            exposed_cluster_candidates.update(
                member.removeprefix("candidate::")
                for member in members
                if member.startswith("candidate::")
            )
    for accession in sorted(exposed_cluster_candidates):
        reasons[accession].append("EXPOSED_CLUSTER_OVERLAP")
    included = [entry for entry in preleakage if not reasons[entry.accession]]
    if not included:
        raise ValueError("no candidates remain after Step 3 screening")

    queries_fasta = output_dir / "queries.fasta"
    _write_queries_fasta(queries_fasta, included)
    cluster_prefix = output_dir / "mmseqs-clusters"
    cluster_command = _cluster_command(
        mmseqs_executable,
        queries_fasta,
        cluster_prefix,
        output_dir / "tmp-query-clusters",
    )
    _run(cluster_command, commands)
    clusters = _read_cluster_tsv(Path(f"{cluster_prefix}_cluster.tsv"))
    ratios = dict(contract["leakage_control"]["split_clusters"]["intended_split"])
    seed = int(contract["random_seed"])
    assignment = assign_cluster_splits(clusters, seed, ratios)
    split_by_accession: dict[str, tuple[str, str]] = {}
    membership_rows: list[dict[str, object]] = []
    for representative, members in sorted(clusters.items()):
        split = assignment[representative]
        for member in sorted(members):
            accession = _parse_accession(member)
            representative_accession = _parse_accession(representative)
            split_by_accession[accession] = (split, representative_accession)
            membership_rows.append(
                {
                    "cluster_representative": representative_accession,
                    "accession": accession,
                    "split": split,
                    "minimum_identity": "0.30",
                    "minimum_query_coverage": "0.80",
                    "minimum_target_coverage": "0.80",
                    "seed": seed,
                }
            )

    alignments = output_dir / "reference_alignments.tsv"
    search_command = [
        mmseqs_executable,
        "easy-search",
        str(queries_fasta),
        str(swissprot_fasta),
        str(alignments),
        str(output_dir / "tmp-reference-search"),
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
    _run(search_command, commands)
    prohibited, difficulty = build_leakage_outputs(
        alignments, included, target_checksums, output_dir
    )

    _write_artifacts(
        output_dir=output_dir,
        nominations=nominations,
        by_accession=by_accession,
        reviewed_accessions=reviewed_accessions,
        exposed_accessions=exposed_accessions,
        entries=entries,
        reasons=reasons,
        included=included,
        split_by_accession=split_by_accession,
        membership_rows=membership_rows,
        prohibited=prohibited,
        difficulty=difficulty,
        source_release=source_release,
    )
    (output_dir / "commands.log").write_text("\n".join(commands) + "\n", encoding="utf-8")

    split_counts = Counter(split for split, _ in split_by_accession.values())
    query_namespace_counts = Counter()
    split_namespace_counts = Counter()
    label_counts = Counter()
    for entry in included:
        namespaces = {
            label.namespace for label in entry.labels if label.admissible_for_primary
        }
        for namespace in namespaces:
            query_namespace_counts[namespace] += 1
            split_namespace_counts[(split_by_accession[entry.accession][0], namespace)] += 1
        for label in entry.labels:
            if label.admissible_for_primary:
                label_counts[label.namespace] += 1
    reason_counts = Counter(reason for values in reasons.values() for reason in values)
    difficulty_counts = Counter(str(row["difficulty_stratum"]) for row in difficulty)
    summary: dict[str, object] = {
        "dataset_id": dataset_id,
        "contract_id": contract["contract_id"],
        "source_release": source_release,
        "nomination_row_count": len(nominations),
        "nomination_accession_count": len(by_accession),
        "reviewed_nomination_accession_count": len(reviewed_accessions),
        "included_query_count": len(included),
        "excluded_reviewed_accession_count": len(reviewed_accessions) - len(included),
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "taxonomy_counts": dict(
            sorted(Counter(entry.superkingdom for entry in included).items())
        ),
        "organism_count": len({entry.organism for entry in included}),
        "cluster_count": len(clusters),
        "split_query_counts": dict(sorted(split_counts.items())),
        "query_namespace_counts": dict(sorted(query_namespace_counts.items())),
        "split_query_namespace_counts": {
            f"{split}:{namespace}": count
            for (split, namespace), count in sorted(split_namespace_counts.items())
        },
        "primary_label_row_counts": dict(sorted(label_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "prohibited_pair_count": len(prohibited),
        "test_labels_sealed": False,
        "scientific_status": "DEVELOPMENT_DATASET_TEST_LABELS_NOT_SEALED",
        "limitations": [
            "Reviewed status in each nomination export is determined only by its Reviewed column.",
            "Frozen Swiss-Prot remains authoritative for sequence and Tier-A labels.",
            "Test labels are present in gold_labels.tsv and must be sealed before "
            "confirmatory use.",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_manifest = {
        "dataset_id": dataset_id,
        "contract": {"path": str(contract_path), "sha256": _sha256_file(contract_path)},
        "nomination_sources": [
            {"path": str(path), "sha256": _sha256_file(path)} for path in nomination_paths
        ],
        "source": {
            "database": "UniProtKB/Swiss-Prot",
            "release": source_release,
            "flat_file": str(swissprot_dat),
            "flat_file_sha256": source_sha256,
            "fasta_file": str(swissprot_fasta),
            "fasta_file_sha256": _sha256_file(swissprot_fasta),
        },
        "exposed_sources": [str(pilot_queries), str(external_panel)],
        "selection": {
            "method": "reviewed nomination union followed by frozen-contract screening",
            "reviewed_field_rule": "case-insensitive exact value reviewed in Reviewed column",
            "seed": seed,
        },
        "mmseqs": {"version": _capture_version(mmseqs_executable)},
    }
    (output_dir / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_paths = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    (output_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(f"{_sha256_file(path)}  {path.name}" for path in artifact_paths) + "\n",
        encoding="utf-8",
    )
    return summary


def _eligibility_reasons(
    entry: SwissProtEntry | None, minimum_length: int, maximum_length: int
) -> list[str]:
    if entry is None:
        return ["NOT_IN_FROZEN_SWISSPROT_RELEASE"]
    reasons: list[str] = []
    if entry.protein_existence != "1":
        reasons.append("NOT_PROTEIN_LEVEL_EVIDENCE")
    if entry.fragment:
        reasons.append("FRAGMENT")
    if not minimum_length <= len(entry.sequence) <= maximum_length:
        reasons.append("LENGTH_OUTSIDE_CONTRACT")
    if not entry.sequence or not set(entry.sequence) <= STANDARD_AMINO_ACIDS:
        reasons.append("INVALID_CANONICAL_SEQUENCE")
    if not any(label.admissible_for_primary for label in entry.labels):
        reasons.append("NO_TIER_A_EC_OR_GO_MF")
    return reasons


def _read_exposed_accessions(pilot_queries: Path, external_panel: Path) -> set[str]:
    exposed: set[str] = set()
    for path in (pilot_queries, external_panel):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None or "accession" not in reader.fieldnames:
                raise ValueError(f"exposed source lacks accession column: {path}")
            exposed.update(row["accession"].strip() for row in reader)
    return exposed


def _cluster_command(
    executable: str, fasta: Path, prefix: Path, tmp_dir: Path
) -> list[str]:
    return [
        executable,
        "easy-cluster",
        str(fasta),
        str(prefix),
        str(tmp_dir),
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


def _write_queries_fasta(path: Path, entries: list[SwissProtEntry]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for entry in sorted(entries, key=lambda item: item.accession):
            handle.write(f">{entry.fasta_id} {entry.protein_name}\n")
            for start in range(0, len(entry.sequence), 80):
                handle.write(entry.sequence[start : start + 80] + "\n")


def _write_artifacts(
    *,
    output_dir: Path,
    nominations: list[Nomination],
    by_accession: dict[str, list[Nomination]],
    reviewed_accessions: set[str],
    exposed_accessions: set[str],
    entries: dict[str, SwissProtEntry],
    reasons: dict[str, list[str]],
    included: list[SwissProtEntry],
    split_by_accession: dict[str, tuple[str, str]],
    membership_rows: list[dict[str, object]],
    prohibited: list[dict[str, object]],
    difficulty: list[dict[str, object]],
    source_release: str,
) -> None:
    included_ids = {entry.accession for entry in included}
    _write_tsv(
        output_dir / "nomination_sources.tsv",
        ["accession", "source_file", "supplied_reviewed_value", "accepted_as_reviewed"],
        (
            {
                "accession": item.accession,
                "source_file": item.source_file,
                "supplied_reviewed_value": item.supplied_reviewed_value,
                "accepted_as_reviewed": str(item.accepted_as_reviewed).lower(),
            }
            for item in nominations
        ),
    )
    _write_tsv(
        output_dir / "screening.tsv",
        [
            "accession",
            "screening_status",
            "exclusion_reasons",
            "reviewed_nomination_sources",
            "all_nomination_sources",
            "present_in_frozen_release",
            "tier_a_gold",
            "sequence_sha256",
        ],
        (
            {
                "accession": accession,
                "screening_status": "INCLUDED" if accession in included_ids else "EXCLUDED",
                "exclusion_reasons": ";".join(reasons.get(accession, [])),
                "reviewed_nomination_sources": ";".join(
                    sorted(
                        Path(item.source_file).name
                        for item in by_accession[accession]
                        if item.accepted_as_reviewed
                    )
                ),
                "all_nomination_sources": ";".join(
                    sorted(Path(item.source_file).name for item in by_accession[accession])
                ),
                "present_in_frozen_release": str(accession in entries).lower(),
                "tier_a_gold": str(
                    accession in entries
                    and any(
                        label.admissible_for_primary for label in entries[accession].labels
                    )
                ).lower(),
                "sequence_sha256": (
                    entries[accession].sequence_sha256 if accession in entries else ""
                ),
            }
            for accession in sorted(reviewed_accessions)
        ),
    )
    _write_tsv(
        output_dir / "exposed_queries.tsv",
        ["accession", "present_in_frozen_release", "sequence_sha256"],
        (
            {
                "accession": accession,
                "present_in_frozen_release": str(accession in entries).lower(),
                "sequence_sha256": (
                    entries[accession].sequence_sha256 if accession in entries else ""
                ),
            }
            for accession in sorted(exposed_accessions)
        ),
    )
    _write_tsv(
        output_dir / "exclusion_ledger.tsv",
        ["accession", "exclusion_reason"],
        (
            {"accession": accession, "exclusion_reason": reason}
            for accession in sorted(reasons)
            for reason in reasons[accession]
        ),
    )
    _write_tsv(
        output_dir / "queries.tsv",
        [
            "accession",
            "fasta_id",
            "canonical_sequence",
            "sequence_sha256",
            "sequence_length",
            "protein_name",
            "organism",
            "taxonomy_id",
            "taxonomy_superkingdom",
            "protein_existence",
            "source_database",
            "source_release",
            "entry_version",
            "split",
            "cluster_representative",
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
                "split": split_by_accession[entry.accession][0],
                "cluster_representative": split_by_accession[entry.accession][1],
            }
            for entry in sorted(included, key=lambda item: item.accession)
        ),
    )
    _write_tsv(
        output_dir / "gold_labels.tsv",
        [
            "accession",
            "split",
            "namespace",
            "identifier",
            "evidence_tier",
            "evidence_code",
            "supporting_reference",
            "source_database",
            "source_release",
            "admissible_for_primary",
            "decision_reason",
        ],
        (
            {
                "accession": entry.accession,
                "split": split_by_accession[entry.accession][0],
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
            for entry in sorted(included, key=lambda item: item.accession)
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
            for entry in sorted(included, key=lambda item: item.accession)
            for namespace, identifiers in (
                ("INTERPRO", entry.interpro_ids),
                ("PFAM", entry.pfam_ids),
            )
            for identifier in identifiers
        ),
    )
    _write_tsv(
        output_dir / "cluster_membership.tsv",
        [
            "cluster_representative",
            "accession",
            "split",
            "minimum_identity",
            "minimum_query_coverage",
            "minimum_target_coverage",
            "seed",
        ],
        membership_rows,
    )
    _write_tsv(
        output_dir / "splits.tsv",
        ["accession", "split", "cluster_representative"],
        (
            {
                "accession": accession,
                "split": values[0],
                "cluster_representative": values[1],
            }
            for accession, values in sorted(split_by_accession.items())
        ),
    )
    _write_tsv(
        output_dir / "prohibited_targets.tsv",
        [
            "query_accession",
            "target_identifier",
            "target_modality",
            "exclusion_reason",
            "sequence_identity",
            "query_coverage",
            "target_coverage",
            "resolution_source",
        ],
        sorted(
            prohibited,
            key=lambda row: (
                str(row["query_accession"]),
                str(row["target_identifier"]),
            ),
        ),
    )
    _write_tsv(
        output_dir / "difficulty_strata.tsv",
        [
            "accession",
            "difficulty_stratum",
            "closest_allowed_reference",
            "sequence_identity",
            "query_coverage",
            "target_coverage",
            "reference_catalog",
        ],
        difficulty,
    )

