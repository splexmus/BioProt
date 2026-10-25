from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import fields as dataclass_fields
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from dualrag.benchmark.dataset import SwissProtEntry, parse_swissprot
from dualrag.config import AlphaFoldApiConfig, FusionConfig, StructureConfig
from dualrag.fasta import read_fasta
from dualrag.fusion.scoring import fuse_candidates
from dualrag.io import file_sha256, stable_hash, write_json, write_tsv
from dualrag.models import (
    CandidateKind,
    FunctionCandidate,
    ProteinQuery,
    SequenceEvidence,
    StructureEvidence,
)
from dualrag.normalization.sequence import normalize as normalize_sequence
from dualrag.normalization.structure import normalize as normalize_structure
from dualrag.structure.alphafold import AcquisitionRecord, acquire_models
from dualrag.structure.foldseek import retrieve as retrieve_structure_foldseek

PREDICTION_FIELDS = [
    "baseline",
    "ablation",
    "query_accession",
    "namespace",
    "identifier",
    "rank",
    "score",
    "modalities",
    "source_ids",
    "mapping_provenance",
]


def run_phase3_benchmark(
    *,
    dataset_dir: Path,
    swissprot_dat: Path,
    output_dir: Path,
    foldseek_db: Path | None,
    foldseek_metadata: Path | None,
    alphafold_cache: Path | None,
    tmp_dir: Path,
    mapping_projection_path: Path | None = None,
    synonym_path: Path | None = None,
    structure_enabled: bool = True,
    resume: bool = False,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    queries = read_fasta(dataset_dir / "queries.fasta")
    query_accessions = {_query_accession(query): query for query in queries}
    prohibited = _prohibited_pairs(dataset_dir / "prohibited_targets.tsv")
    sequence_hits = build_sequence_reference_hits(
        queries=queries,
        alignments_path=dataset_dir / "reference_alignments.tsv",
        swissprot_dat=swissprot_dat,
        prohibited=prohibited,
        top_k=10,
    )
    write_tsv(
        raw_dir / "sequence_evidence.tsv",
        [hit.to_row() for hit in sequence_hits],
        [item.name for item in dataclass_fields(SequenceEvidence)],
    )

    acquisition_records: list[AcquisitionRecord] = []
    structure_hits: list[StructureEvidence] = []
    structure_exclusions: list[dict[str, object]] = []
    if structure_enabled:
        if foldseek_db is None or foldseek_metadata is None or alphafold_cache is None:
            raise ValueError(
                "structure retrieval requires Foldseek DB, metadata, and AlphaFold cache"
            )
        structure_hits, acquisition_records, structure_exclusions = _structure_hits(
            queries=queries,
            foldseek_db=foldseek_db,
            foldseek_metadata=foldseek_metadata,
            alphafold_cache=alphafold_cache,
            tmp_dir=tmp_dir,
            raw_dir=raw_dir,
            prohibited=prohibited,
            resume=resume,
        )
    write_tsv(
        raw_dir / "structure_evidence.tsv",
        [hit.to_row() for hit in structure_hits],
        [item.name for item in dataclass_fields(StructureEvidence)],
    )
    write_tsv(
        raw_dir / "alphafold_acquisition.tsv",
        [record.to_row() for record in acquisition_records],
        [item.name for item in dataclass_fields(AcquisitionRecord)],
    )
    write_tsv(
        raw_dir / "structure_exclusions.tsv",
        structure_exclusions,
        ["query_accession", "target_structure_id", "target_uniprot_id", "reason"],
    )

    projections = _load_projections(mapping_projection_path)
    variants = {
        "NO_MAPPING": (False, False, None),
        "INTERPRO2GO": (True, False, None),
        "GO_EC_MAPPING": (False, True, None),
        "CURATED_GO_SYNONYMS": (False, False, synonym_path),
        "ALL_MAPPINGS": (True, True, synonym_path),
    }
    all_predictions: list[dict[str, object]] = []
    all_candidates: list[dict[str, object]] = []
    for ablation, (use_interpro, use_ec, current_synonyms) in variants.items():
        seq_variant = _project_sequence_hits(sequence_hits, projections, use_ec=use_ec)
        struct_variant = _project_structure_hits(
            structure_hits,
            projections,
            use_interpro=use_interpro,
            use_ec=use_ec,
        )
        for baseline, seq_current, struct_current in (
            ("B2_SEQUENCE_ONLY", seq_variant, []),
            ("B3_STRUCTURE_ONLY", [], struct_variant),
            ("B4_DUAL_DETERMINISTIC", seq_variant, struct_variant),
        ):
            config = FusionConfig(mapping_path=None, synonym_path=current_synonyms)
            result = fuse_candidates(
                queries,
                seq_current,
                struct_current,
                config,
                run_id=stable_hash(
                    {"dataset": dataset_dir.name, "baseline": baseline, "ablation": ablation}
                )[:16],
                parameters_hash=stable_hash(
                    {
                        "baseline": baseline,
                        "ablation": ablation,
                        "projection": str(mapping_projection_path),
                        "synonyms": str(current_synonyms),
                    }
                ),
            )
            all_candidates.extend(
                {
                    **candidate.to_row(),
                    "baseline": baseline,
                    "ablation": ablation,
                }
                for candidate in result.candidates
            )
            all_predictions.extend(_prediction_rows(result.candidates, baseline, ablation))

    principal = [row for row in all_predictions if row["ablation"] == "ALL_MAPPINGS"]
    write_tsv(output_dir / "predictions.tsv", principal, PREDICTION_FIELDS)
    write_tsv(output_dir / "ablation_predictions.tsv", all_predictions, PREDICTION_FIELDS)
    candidate_fields = [
        "baseline",
        "ablation",
        *[item.name for item in dataclass_fields(FunctionCandidate)],
    ]
    write_tsv(output_dir / "ablation_candidates.tsv", all_candidates, candidate_fields)

    status_counts: dict[str, int] = defaultdict(int)
    for record in acquisition_records:
        status_counts[record.status] += 1
    summary: dict[str, object] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_id": dataset_dir.name,
        "query_count": len(query_accessions),
        "sequence_allowed_hit_count": len(sequence_hits),
        "structure_allowed_hit_count": len(structure_hits),
        "structure_exclusion_count": len(structure_exclusions),
        "alphafold_status_counts": dict(sorted(status_counts.items())),
        "principal_prediction_count": len(principal),
        "ablation_prediction_count": len(all_predictions),
        "mapping_projection": _input_record(mapping_projection_path),
        "synonyms": _input_record(synonym_path),
        "strict_primary_limitations": [
            "B2 uses MMseqs2 against frozen Swiss-Prot rather than eggNOG seed-ortholog output, "
            "because eggNOG-mapper does not expose a rankable leakage-filterable hit list.",
            "B3 excludes PDB chains without SIFTS-resolved UniProt accessions.",
            "Structure homology exclusions use the precomputed Swiss-Prot sequence catalog, "
            "not Foldseek fident.",
        ],
    }
    write_json(output_dir / "retrieval_summary.json", summary)
    return summary


def build_sequence_reference_hits(
    *,
    queries: list[ProteinQuery],
    alignments_path: Path,
    swissprot_dat: Path,
    prohibited: set[tuple[str, str]],
    top_k: int,
) -> list[SequenceEvidence]:
    query_by_accession = {_query_accession(query): query for query in queries}
    selected_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    target_accessions: set[str] = set()
    fields = ["query", "target", "fident", "qcov", "tcov", "evalue", "bits"]
    with alignments_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, fieldnames=fields, delimiter="\t"):
            accession = _identifier_accession(row["query"])
            target = _identifier_accession(row["target"])
            if accession not in query_by_accession or (accession, target) in prohibited:
                continue
            if len(selected_rows[accession]) >= top_k:
                continue
            selected_rows[accession].append(row)
            target_accessions.add(target)

    metadata: dict[str, SwissProtEntry] = {}
    for entry in parse_swissprot(swissprot_dat):
        if entry.accession in target_accessions:
            metadata[entry.accession] = entry
            if len(metadata) == len(target_accessions):
                break
    missing = target_accessions - metadata.keys()
    if missing:
        raise ValueError(f"Swiss-Prot metadata missing for targets: {sorted(missing)[:5]}")

    hits: list[SequenceEvidence] = []
    for accession, query in query_by_accession.items():
        for row in selected_rows[accession]:
            target = _identifier_accession(row["target"])
            entry = metadata[target]
            hit = SequenceEvidence(
                query_id=query.query_id,
                target_id=target,
                tool="MMseqs2",
                tool_version="16.747c6",
                database="UniProtKB/Swiss-Prot",
                database_version="2026_03",
                sequence_identity=float(row["fident"]),
                alignment_coverage=min(float(row["qcov"]), float(row["tcov"])),
                evalue=float(row["evalue"]),
                bitscore=float(row["bits"]),
                protein_name=entry.protein_name,
                go_terms=sorted(
                    {label.identifier for label in entry.labels if label.namespace == "GO_MF"}
                ),
                ec_numbers=sorted(
                    {label.identifier for label in entry.labels if label.namespace == "EC"}
                ),
                interpro_ids=entry.interpro_ids,
                pfam_ids=entry.pfam_ids,
                raw_output_path=str(alignments_path),
                source_accession=target,
            )
            normalize_sequence(hit, "phase3-sequence-v1")
            hits.append(hit)
    return hits


def _structure_hits(
    *,
    queries: list[ProteinQuery],
    foldseek_db: Path,
    foldseek_metadata: Path,
    alphafold_cache: Path,
    tmp_dir: Path,
    raw_dir: Path,
    prohibited: set[tuple[str, str]],
    resume: bool,
) -> tuple[list[StructureEvidence], list[AcquisitionRecord], list[dict[str, object]]]:
    structure_raw = raw_dir / "structure"
    api_config = AlphaFoldApiConfig(enabled=True, request_interval_seconds=0.2)
    models, acquisitions = acquire_models(
        queries, alphafold_cache, structure_raw / "alphafold", api_config
    )
    config = StructureConfig(
        backend="hybrid",
        foldseek_db=foldseek_db,
        target_metadata=foldseek_metadata,
        alphafold_cache=alphafold_cache,
        alphafold_api=api_config,
        database_name="Foldseek-PDB",
        database_version="PDB 2025-01-01; SIFTS 2026-10-04",
        top_k=100,
        executable="foldseek",
        threads=8,
        sensitivity=7.5,
    )
    cached_results = structure_raw / "foldseek" / "foldseek_hits.tsv"
    if resume and cached_results.is_file():
        from dualrag.structure.foldseek import parse_results

        safe_to_query = {
            f"q{index:06d}": query.query_id
            for index, query in enumerate(queries)
            if query.query_id in models
        }
        unfiltered = parse_results(cached_results, safe_to_query, config)
    else:
        unfiltered, _command = retrieve_structure_foldseek(
            queries,
            models,
            structure_raw / "foldseek",
            tmp_dir / stable_hash([query.query_id for query in queries])[:16],
            config,
        )
    allowed: dict[str, list[StructureEvidence]] = defaultdict(list)
    exclusions: list[dict[str, object]] = []
    for hit in unfiltered:
        accession = _identifier_accession(hit.query_id)
        targets = [value for value in (hit.target_uniprot_id or "").split(";") if value]
        reason = ""
        if not targets:
            reason = "UNRESOLVED_SIFTS_ACCESSION"
        elif any((accession, target) in prohibited for target in targets):
            reason = "PROHIBITED_SEQUENCE_HOMOLOGY"
        if reason:
            exclusions.append(
                {
                    "query_accession": accession,
                    "target_structure_id": hit.target_structure_id,
                    "target_uniprot_id": hit.target_uniprot_id or "",
                    "reason": reason,
                }
            )
            continue
        if len(allowed[hit.query_id]) < 10:
            normalize_structure(hit, "phase3-structure-v1")
            allowed[hit.query_id].append(hit)
    return [hit for query in queries for hit in allowed[query.query_id]], acquisitions, exclusions


def _load_projections(path: Path | None) -> dict[str, dict[str, set[str]]]:
    projections: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if path is None:
        return projections
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            projections[row["mapping_type"]][row["source_id"]].add(row["target_id"])
    return projections


def _project_sequence_hits(
    hits: list[SequenceEvidence],
    projections: dict[str, dict[str, set[str]]],
    *,
    use_ec: bool,
) -> list[SequenceEvidence]:
    projected: list[SequenceEvidence] = []
    for hit in hits:
        go_terms = set(hit.go_terms)
        if use_ec:
            for ec_number in hit.ec_numbers:
                go_terms.update(projections["EC2GO"].get(f"EC:{ec_number}", set()))
        projected.append(replace(hit, go_terms=sorted(go_terms)))
    return projected


def _project_structure_hits(
    hits: list[StructureEvidence],
    projections: dict[str, dict[str, set[str]]],
    *,
    use_interpro: bool,
    use_ec: bool,
) -> list[StructureEvidence]:
    projected: list[StructureEvidence] = []
    for hit in hits:
        go_terms = set(hit.go_terms)
        if use_interpro:
            for interpro_id in hit.interpro_ids:
                go_terms.update(projections["INTERPRO2GO"].get(interpro_id, set()))
        if use_ec:
            for ec_number in hit.ec_numbers:
                go_terms.update(projections["EC2GO"].get(f"EC:{ec_number}", set()))
        projected.append(replace(hit, go_terms=sorted(go_terms)))
    return projected


def _prediction_rows(
    candidates: list[FunctionCandidate], baseline: str, ablation: str
) -> list[dict[str, object]]:
    by_query_namespace: dict[tuple[str, str], list[FunctionCandidate]] = defaultdict(list)
    for candidate in candidates:
        namespace = {
            CandidateKind.EC: "EC",
            CandidateKind.GO: "GO_MF",
        }.get(candidate.candidate_kind)
        if namespace and candidate.informative:
            by_query_namespace[(_identifier_accession(candidate.query_id), namespace)].append(
                candidate
            )
    rows: list[dict[str, object]] = []
    for (accession, namespace), values in sorted(by_query_namespace.items()):
        ordered = sorted(values, key=lambda item: (-item.rerank_score, item.candidate_id))
        for rank, candidate in enumerate(ordered, start=1):
            rows.append(
                {
                    "baseline": baseline,
                    "ablation": ablation,
                    "query_accession": accession,
                    "namespace": namespace,
                    "identifier": candidate.candidate_id,
                    "rank": rank,
                    "score": candidate.rerank_score,
                    "modalities": ";".join(candidate.modalities),
                    "source_ids": ";".join(
                        sorted(set(candidate.sequence_source_ids + candidate.structure_source_ids))
                    ),
                    "mapping_provenance": ";".join(candidate.mapping_provenance),
                }
            )
    return rows


def _prohibited_pairs(path: Path) -> set[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            (row["query_accession"], row["target_identifier"])
            for row in csv.DictReader(handle, delimiter="\t")
        }


def _query_accession(query: ProteinQuery) -> str:
    return _identifier_accession(query.query_id)


def _identifier_accession(identifier: str) -> str:
    parts = identifier.split("|")
    return parts[1] if len(parts) >= 3 else identifier.split()[0]


def _input_record(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return {"path": str(path), "sha256": file_sha256(path)}
