from __future__ import annotations

import json
import re
from collections import Counter
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
    build_leakage_outputs,
    parse_swissprot,
)
from dualrag.fasta import read_fasta


@dataclass(frozen=True)
class PanelCandidate:
    accession: str
    supplied_taxonomy_group: str
    supplied_protein_name: str
    supplied_biological_role: str
    supplied_site_group: str
    supplied_architecture: str


def parse_panel_markdown(path: Path) -> list[PanelCandidate]:
    """Parse the six-column protein tables from the supplied Markdown panel."""
    group = ""
    candidates: list[PanelCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            group = line.removeprefix("## ").strip()
            continue
        if not re.match(r"^\|\s*`[A-Z0-9]+`\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            raise ValueError(f"expected five panel columns, observed {len(cells)}: {line}")
        candidates.append(
            PanelCandidate(
                accession=cells[0].strip("`"),
                supplied_taxonomy_group=group,
                supplied_protein_name=cells[1],
                supplied_biological_role=cells[2],
                supplied_site_group=cells[3],
                supplied_architecture=cells[4].rstrip("*"),
            )
        )
    accessions = [candidate.accession for candidate in candidates]
    if not candidates:
        raise ValueError(f"no protein rows found in {path}")
    if len(accessions) != len(set(accessions)):
        raise ValueError("panel contains duplicate accessions")
    return candidates


def build_panel_case_dataset(
    *,
    panel_markdown: Path,
    swissprot_dat: Path,
    swissprot_fasta: Path,
    pilot_dataset: Path,
    contract_path: Path,
    output_dir: Path,
    dataset_id: str,
    source_release: str,
    source_sha256: str,
    mmseqs_executable: str = "mmseqs",
    resume: bool = False,
) -> dict[str, object]:
    """Screen an accession panel and materialize it as an independent benchmark case."""
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if _sha256_file(swissprot_dat) != source_sha256:
        raise ValueError("Swiss-Prot flat-file checksum does not match the declared release")
    minimum_length = int(contract["gold_standard"]["inclusion"]["minimum_length"])
    maximum_length = int(contract["gold_standard"]["inclusion"]["maximum_length"])
    candidates = parse_panel_markdown(panel_markdown)
    requested = {candidate.accession for candidate in candidates}
    entries: dict[str, SwissProtEntry] = {}
    target_checksums: dict[str, str] = {}
    for entry in parse_swissprot(swissprot_dat):
        target_checksums[entry.accession] = entry.sequence_sha256
        if entry.accession in requested:
            entries[entry.accession] = entry

    pilot_accessions = {
        _parse_accession(query.query_id) for query in read_fasta(pilot_dataset / "queries.fasta")
    }
    reasons: dict[str, list[str]] = {}
    precluster_entries: list[SwissProtEntry] = []
    for candidate in candidates:
        entry = entries.get(candidate.accession)
        current: list[str] = []
        if entry is None:
            current.append("NOT_IN_FROZEN_SWISSPROT_RELEASE")
        else:
            if entry.protein_existence != "1":
                current.append("NOT_PROTEIN_LEVEL_EVIDENCE")
            if entry.fragment:
                current.append("FRAGMENT")
            if not minimum_length <= len(entry.sequence) <= maximum_length:
                current.append("LENGTH_OUTSIDE_CONTRACT")
            if not entry.sequence or not set(entry.sequence) <= STANDARD_AMINO_ACIDS:
                current.append("INVALID_CANONICAL_SEQUENCE")
            if not any(label.admissible_for_primary for label in entry.labels):
                current.append("NO_TIER_A_EC_OR_GO_MF")
            if candidate.accession in pilot_accessions:
                current.append("EXACT_PILOT_ACCESSION_OVERLAP")
        reasons[candidate.accession] = current
        if entry is not None and not current:
            precluster_entries.append(entry)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        output_dir / "panel_input.tsv",
        [
            "accession",
            "supplied_taxonomy_group",
            "supplied_protein_name",
            "supplied_biological_role",
            "supplied_site_group",
            "supplied_architecture",
        ],
        (
            {
                "accession": candidate.accession,
                "supplied_taxonomy_group": candidate.supplied_taxonomy_group,
                "supplied_protein_name": candidate.supplied_protein_name,
                "supplied_biological_role": candidate.supplied_biological_role,
                "supplied_site_group": candidate.supplied_site_group,
                "supplied_architecture": candidate.supplied_architecture,
            }
            for candidate in candidates
        ),
    )
    command_log: list[str] = []
    overlap_fasta = output_dir / "pilot-panel-overlap.fasta"
    if not (resume and overlap_fasta.exists()):
        with overlap_fasta.open("w", encoding="utf-8") as handle:
            for query in read_fasta(pilot_dataset / "queries.fasta"):
                handle.write(f">pilot::{_parse_accession(query.query_id)}\n{query.sequence}\n")
            for entry in precluster_entries:
                handle.write(f">panel::{entry.accession}\n{entry.sequence}\n")
    overlap_prefix = output_dir / "pilot-panel-clusters"
    overlap_tsv = Path(f"{overlap_prefix}_cluster.tsv")
    overlap_command = [
        mmseqs_executable,
        "easy-cluster",
        str(overlap_fasta),
        str(overlap_prefix),
        str(output_dir / "tmp-overlap"),
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
    if resume and overlap_tsv.exists():
        command_log.append(
            f"REUSED existing {overlap_tsv}; original command: {' '.join(overlap_command)}"
        )
    else:
        _run(overlap_command, command_log)
    for members in _read_cluster_tsv(overlap_tsv).values():
        has_pilot = any(member.startswith("pilot::") for member in members)
        if has_pilot:
            for member in members:
                if member.startswith("panel::"):
                    reasons[member.removeprefix("panel::")].append("PILOT_CLUSTER_OVERLAP")

    included = [
        entries[candidate.accession]
        for candidate in candidates
        if candidate.accession in entries and not reasons[candidate.accession]
    ]
    queries_fasta = output_dir / "queries.fasta"
    with queries_fasta.open("w", encoding="utf-8") as handle:
        for entry in included:
            handle.write(f">{entry.fasta_id} {entry.protein_name}\n")
            for start in range(0, len(entry.sequence), 80):
                handle.write(entry.sequence[start : start + 80] + "\n")

    _write_queries_and_labels(output_dir, included, source_release)
    cluster_prefix = output_dir / "mmseqs-clusters"
    cluster_tsv = Path(f"{cluster_prefix}_cluster.tsv")
    cluster_command = [
        mmseqs_executable,
        "easy-cluster",
        str(queries_fasta),
        str(cluster_prefix),
        str(output_dir / "tmp-cluster"),
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
    membership: list[dict[str, object]] = []
    for representative, members in sorted(clusters.items()):
        for member in sorted(members):
            membership.append(
                {
                    "cluster_representative": _parse_accession(representative),
                    "accession": _parse_accession(member),
                    "split": "external_case",
                    "minimum_identity": "0.30",
                    "minimum_query_coverage": "0.80",
                    "minimum_target_coverage": "0.80",
                    "seed": contract["random_seed"],
                }
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
        membership,
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
            for row in membership
        ),
    )

    alignments_path = output_dir / "reference_alignments.tsv"
    search_command = [
        mmseqs_executable,
        "easy-search",
        str(queries_fasta),
        str(swissprot_fasta),
        str(alignments_path),
        str(output_dir / "tmp-search"),
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
        alignments_path, included, target_checksums, output_dir
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
            prohibited, key=lambda row: (str(row["query_accession"]), str(row["target_identifier"]))
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
    difficulty_by_accession = {str(row["accession"]): row for row in difficulty}
    screening_rows: list[dict[str, object]] = []
    case_rows: list[dict[str, object]] = []
    for candidate in candidates:
        entry = entries.get(candidate.accession)
        difficulty_row = difficulty_by_accession.get(candidate.accession, {})
        identity = difficulty_row.get("sequence_identity", "")
        low_identity = bool(identity != "" and float(str(identity)) <= 0.30)
        observed_site_group = (
            "ACTIVE_SITE_UNKNOWN"
            if entry is None
            else (
                "ANNOTATED_ACTIVE_SITE" if entry.active_site_count else "NO_ANNOTATED_ACTIVE_SITE"
            )
        )
        supplied_site_group = {
            "Low-site": "NO_ANNOTATED_ACTIVE_SITE",
            "Annotated-site": "ANNOTATED_ACTIVE_SITE",
        }.get(candidate.supplied_site_group, "ACTIVE_SITE_UNKNOWN")
        screening_rows.append(
            {
                "accession": candidate.accession,
                "screening_status": "INCLUDED_EXTERNAL_CASE"
                if not reasons[candidate.accession]
                else "EXCLUDED",
                "exclusion_reasons": ";".join(reasons[candidate.accession]),
                "present_in_frozen_release": str(entry is not None).lower(),
                "tier_a_gold": str(
                    bool(entry and any(label.admissible_for_primary for label in entry.labels))
                ).lower(),
                "pilot_cluster_overlap": str(
                    "PILOT_CLUSTER_OVERLAP" in reasons[candidate.accession]
                ).lower(),
                "closest_allowed_identity": identity,
                "low_identity_eligible": str(low_identity).lower(),
                "active_site_group_supplied": supplied_site_group,
                "active_site_group_frozen_record": observed_site_group,
                "active_site_annotation_count": entry.active_site_count if entry else "",
                "architecture_group_supplied": candidate.supplied_architecture.upper(),
                "architecture_verification": (
                    "PROVISIONAL_UNCONFIRMED_NO_POSITIONAL_INTERPRO_SOURCE"
                ),
            }
        )
        if not reasons[candidate.accession]:
            case_rows.append(
                {
                    "accession": candidate.accession,
                    "case_group": "SUPPLIED_PANEL_2026_10_26",
                    "low_identity_eligible": str(low_identity).lower(),
                    "active_site_group": observed_site_group,
                    "supplied_architecture_group": candidate.supplied_architecture.upper(),
                    "architecture_verification": (
                        "PROVISIONAL_UNCONFIRMED_NO_POSITIONAL_INTERPRO_SOURCE"
                    ),
                    "supplied_taxonomy_group": candidate.supplied_taxonomy_group,
                    "supplied_biological_role": candidate.supplied_biological_role,
                }
            )
    screening_fields = list(screening_rows[0])
    _write_tsv(output_dir / "panel_screening.tsv", screening_fields, screening_rows)
    _write_tsv(output_dir / "case_metadata.tsv", list(case_rows[0]), case_rows)
    (output_dir / "commands.log").write_text("\n".join(command_log) + "\n", encoding="utf-8")

    summary: dict[str, object] = {
        "dataset_id": dataset_id,
        "case_type": "external_candidate_panel",
        "supplied_candidate_count": len(candidates),
        "included_query_count": len(included),
        "excluded_candidate_count": len(candidates) - len(included),
        "exclusion_reason_counts": dict(
            sorted(Counter(reason for values in reasons.values() for reason in values).items())
        ),
        "low_identity_eligible_count": sum(
            row["low_identity_eligible"] == "true" for row in case_rows
        ),
        "cluster_count": len(clusters),
        "prohibited_pair_count": len(prohibited),
        "source_release": source_release,
        "limitations": [
            "This external case does not alter the frozen pilot "
            "development/validation/test splits.",
            "Architecture labels remain provisional because no release-matched "
            "positional InterProScan source was available.",
            "NO_ANNOTATED_ACTIVE_SITE means no UniProt ACT_SITE feature; "
            "it does not imply biological inactivity.",
            "Only included records are evaluated; every supplied exclusion remains "
            "in panel_screening.tsv.",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "dataset_id": dataset_id,
        "panel_source": {"path": str(panel_markdown), "sha256": _sha256_file(panel_markdown)},
        "contract": {"path": str(contract_path), "sha256": _sha256_file(contract_path)},
        "pilot_dataset": {
            "path": str(pilot_dataset),
            "queries_sha256": _sha256_file(pilot_dataset / "queries.fasta"),
        },
        "source": {
            "database": "UniProtKB/Swiss-Prot",
            "release": source_release,
            "flat_file": str(swissprot_dat),
            "flat_file_sha256": source_sha256,
            "fasta_file": str(swissprot_fasta),
            "fasta_file_sha256": _sha256_file(swissprot_fasta),
        },
        "mmseqs": {"version": _capture_version(mmseqs_executable), "commands_log": "commands.log"},
    }
    (output_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_paths = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    (output_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(f"{_sha256_file(path)}  {path.name}" for path in artifact_paths) + "\n",
        encoding="utf-8",
    )
    return summary


def _write_queries_and_labels(
    output_dir: Path, entries: list[SwissProtEntry], source_release: str
) -> None:
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
            "inclusion_status",
            "inclusion_or_exclusion_reason",
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
                "inclusion_status": "INCLUDED_EXTERNAL_CASE",
                "inclusion_or_exclusion_reason": "passes frozen-source panel screening",
            }
            for entry in entries
        ),
    )
    _write_tsv(
        output_dir / "gold_labels.tsv",
        [
            "accession",
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
