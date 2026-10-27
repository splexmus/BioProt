from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LiteratureSource(StrEnum):
    PUBMED = "PUBMED"
    PMC_OPEN_ACCESS = "PMC_OPEN_ACCESS"


class FullTextStatus(StrEnum):
    PMC_OPEN_ACCESS = "PMC_OPEN_ACCESS"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    NOT_OPEN_ACCESS = "NOT_OPEN_ACCESS"
    NOT_FOUND = "NOT_FOUND"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"


class SectionType(StrEnum):
    TITLE_ABSTRACT = "TITLE_ABSTRACT"
    INTRODUCTION = "INTRODUCTION"
    METHODS = "METHODS"
    RESULTS = "RESULTS"
    DISCUSSION = "DISCUSSION"
    FIGURE_CAPTION = "FIGURE_CAPTION"
    TABLE_CAPTION = "TABLE_CAPTION"
    OTHER = "OTHER"


class EvidenceRole(StrEnum):
    SUPPORT = "SUPPORT"
    CONTRADICTION = "CONTRADICTION"
    BACKGROUND = "BACKGROUND"
    IRRELEVANT = "IRRELEVANT"
    UNASSESSED = "UNASSESSED"


class AssignmentMethod(StrEnum):
    UNASSESSED = "UNASSESSED"
    MANUAL = "MANUAL"
    RULE_BASED = "RULE_BASED"
    MODEL = "MODEL"


class EntityMatch(StrEnum):
    EXACT_ACCESSION = "EXACT_ACCESSION"
    EXACT_NAMED_PROTEIN = "EXACT_NAMED_PROTEIN"
    TRACEABLE_HOMOLOG = "TRACEABLE_HOMOLOG"
    FAMILY_ONLY = "FAMILY_ONLY"
    NONE = "NONE"
    UNRESOLVED = "UNRESOLVED"


class OrganismMatch(StrEnum):
    EXACT_TAXON = "EXACT_TAXON"
    SAME_SPECIES = "SAME_SPECIES"
    RELATED_TAXON = "RELATED_TAXON"
    HETEROLOGOUS_SYSTEM = "HETEROLOGOUS_SYSTEM"
    MISMATCH = "MISMATCH"
    UNRESOLVED = "UNRESOLVED"


class EvidenceModality(StrEnum):
    SEQUENCE = "SEQUENCE"
    STRUCTURE = "STRUCTURE"
    DOMAIN_ONTOLOGY = "DOMAIN_ONTOLOGY"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: int = Field(default=1, ge=1)


class SelectedHomolog(ContractModel):
    accession: str = Field(min_length=1)
    source_target_id: str = Field(min_length=1)
    sequence_identity: float | None = Field(default=None, ge=0, le=1)
    alignment_coverage: float | None = Field(default=None, ge=0, le=1)
    normalized_score: float | None = Field(default=None, ge=0, le=1)
    provenance: str = Field(min_length=1)


class LiteratureQuery(ContractModel):
    query_id: str = Field(min_length=1)
    query_accession: str | None = None
    protein_name: str | None = None
    organism: str | None = None
    taxonomy_id: int | None = Field(default=None, ge=1)
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_labels: list[str] = Field(default_factory=list)
    selected_homologs: list[SelectedHomolog] = Field(default_factory=list)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    cross_modal_status: str
    query_terms: list[str] = Field(min_length=1)
    query_variants: list[str] = Field(min_length=1)
    query_builder_version: str = Field(min_length=1)
    source_biological_run_id: str = Field(min_length=1)
    source_parameters_hash: str = Field(min_length=1)
    created_at: datetime

    @field_validator(
        "candidate_ids",
        "candidate_labels",
        "alternative_hypotheses",
        "query_terms",
        "query_variants",
    )
    @classmethod
    def unique_nonempty_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("list values must be unique")
        return cleaned

    @model_validator(mode="after")
    def has_protein_identity(self) -> LiteratureQuery:
        if not self.query_accession and not self.protein_name:
            raise ValueError("query_accession or protein_name is required")
        accessions = [homolog.accession for homolog in self.selected_homologs]
        if len(accessions) != len(set(accessions)):
            raise ValueError("selected homolog accessions must be unique")
        _require_timezone(self.created_at, "created_at")
        return self


class ArticleMetadata(ContractModel):
    source_article_id: str = Field(min_length=1)
    source: LiteratureSource
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str = Field(min_length=1)
    abstract: str | None = None
    year: int | None = Field(default=None, ge=1600, le=2200)
    journal: str | None = None
    publication_types: list[str] = Field(default_factory=list)
    abstract_sections: list[dict[str, str]] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    related_articles: list[dict[str, str]] = Field(default_factory=list)
    is_review: bool = False
    source_organisms: list[str] = Field(default_factory=list)
    source_taxonomy_ids: list[int] = Field(default_factory=list)
    assay_hosts: list[str] = Field(default_factory=list)
    protein_accessions: list[str] = Field(default_factory=list)
    source_url: str = Field(min_length=1)
    full_text_status: FullTextStatus
    retrieved_at: datetime
    raw_record_path: str | None = None
    raw_record_sha256: str | None = None
    license: str | None = None
    acquisition_error: str | None = None

    @model_validator(mode="after")
    def validate_identity_and_source(self) -> ArticleMetadata:
        if not any((self.pmid, self.pmcid, self.doi, self.source_article_id)):
            raise ValueError("at least one article identifier is required")
        if self.source is LiteratureSource.PMC_OPEN_ACCESS and not self.pmcid:
            raise ValueError("PMC_OPEN_ACCESS articles require a PMCID")
        if self.full_text_status is FullTextStatus.PMC_OPEN_ACCESS and not self.pmcid:
            raise ValueError("PMC_OPEN_ACCESS full text requires a PMCID")
        _require_timezone(self.retrieved_at, "retrieved_at")
        return self


class LiteratureChunk(ContractModel):
    chunk_id: str = Field(min_length=1)
    source_article_id: str = Field(min_length=1)
    source: LiteratureSource
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str = Field(min_length=1)
    year: int | None = Field(default=None, ge=1600, le=2200)
    journal: str | None = None
    article_is_review: bool = False
    full_text_status: FullTextStatus
    organism_context: list[str] = Field(default_factory=list)
    section_type: SectionType
    section_title: str | None = None
    text: str = Field(min_length=1, max_length=1200)
    start_character: int = Field(ge=0)
    end_character: int = Field(gt=0)
    source_url: str = Field(min_length=1)
    retrieved_at: datetime
    chunker_version: str = Field(min_length=1)
    text_sha256: str | None = None

    @model_validator(mode="after")
    def validate_offsets_and_checksum(self) -> LiteratureChunk:
        if self.end_character <= self.start_character:
            raise ValueError("end_character must be greater than start_character")
        expected = hashlib.sha256(self.text.encode()).hexdigest()
        if self.text_sha256 is None:
            self.text_sha256 = expected
        elif self.text_sha256 != expected:
            raise ValueError("text_sha256 does not match text")
        _require_timezone(self.retrieved_at, "retrieved_at")
        return self


class LiteratureHit(ContractModel):
    hit_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    chunk: LiteratureChunk
    rank: int = Field(ge=1)
    retrieval_score: float
    lexical_score: float | None = None
    vector_score: float | None = None
    reranker_score: float | None = None
    retrieval_method: str = Field(min_length=1)
    retriever_version: str = Field(min_length=1)
    reranker_version: str | None = None
    query_terms: list[str] = Field(min_length=1)
    retrieved_at: datetime
    entity_match: EntityMatch = EntityMatch.UNRESOLVED
    entity_match_basis: list[str] = Field(default_factory=list)
    organism_match: OrganismMatch = OrganismMatch.UNRESOLVED
    source_organism: str | None = None
    assay_host: str | None = None
    evidence_role: EvidenceRole = EvidenceRole.UNASSESSED
    assignment_method: AssignmentMethod = AssignmentMethod.UNASSESSED
    assignment_version: str | None = None
    is_primary_experiment: bool | None = None
    uncertainty_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assignment(self) -> LiteratureHit:
        if self.evidence_role in {EvidenceRole.SUPPORT, EvidenceRole.CONTRADICTION}:
            if self.chunk.article_is_review:
                raise ValueError("review passages cannot be support or contradiction")
            if self.is_primary_experiment is not True:
                raise ValueError("support or contradiction requires a primary experiment")
            if self.assignment_method is AssignmentMethod.UNASSESSED:
                raise ValueError("assessed evidence requires an assignment method")
            if not self.entity_match_basis:
                raise ValueError("support or contradiction requires an entity-match basis")
        if (
            self.evidence_role is EvidenceRole.UNASSESSED
            and self.assignment_method is not AssignmentMethod.UNASSESSED
        ):
            raise ValueError("unassessed evidence must use UNASSESSED assignment method")
        _require_timezone(self.retrieved_at, "retrieved_at")
        return self


class LiteratureCandidate(ContractModel):
    candidate_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    chunk: LiteratureChunk
    lexical_score: float = Field(ge=0, le=1)
    vector_score: float = Field(ge=0, le=1)
    hybrid_score: float = Field(ge=0, le=1)
    reranker_score: float = Field(ge=0, le=1)
    lexical_rank: int = Field(ge=1)
    vector_rank: int = Field(ge=1)
    hybrid_rank: int = Field(ge=1)
    reranker_rank: int = Field(ge=1)
    entity_match: EntityMatch = EntityMatch.UNRESOLVED
    entity_match_basis: list[str] = Field(default_factory=list)
    organism_match: OrganismMatch = OrganismMatch.UNRESOLVED
    is_primary_experiment: bool | None = None
    retriever_version: str = Field(min_length=1)
    reranker_version: str = Field(min_length=1)
    scored_at: datetime

    @model_validator(mode="after")
    def validate_query_and_time(self) -> LiteratureCandidate:
        _require_timezone(self.scored_at, "scored_at")
        return self


class BiologicalEvidenceReference(ContractModel):
    modality: EvidenceModality
    candidate_id: str = Field(min_length=1)
    score: float
    source_ids: list[str] = Field(min_length=1)
    run_id: str = Field(min_length=1)
    parameters_hash: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)


class EvidencePacket(ContractModel):
    packet_id: str = Field(min_length=1)
    contract_id: str = "phase4-literature-v1"
    query: LiteratureQuery
    biological_evidence: list[BiologicalEvidenceReference] = Field(default_factory=list)
    literature_hits: list[LiteratureHit] = Field(max_length=20)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    contradiction_hit_ids: list[str] = Field(default_factory=list)
    claim_boundaries: list[str] = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def validate_packet_links_and_limits(self) -> EvidencePacket:
        hit_ids = [hit.hit_id for hit in self.literature_hits]
        if len(hit_ids) != len(set(hit_ids)):
            raise ValueError("literature hit IDs must be unique")
        if any(hit.query_id != self.query.query_id for hit in self.literature_hits):
            raise ValueError("all literature hits must match the packet query")
        contradiction_ids = {
            hit.hit_id
            for hit in self.literature_hits
            if hit.evidence_role is EvidenceRole.CONTRADICTION
        }
        if set(self.contradiction_hit_ids) != contradiction_ids:
            raise ValueError("contradiction_hit_ids must exactly reference contradiction hits")
        article_counts: dict[str, int] = {}
        for hit in self.literature_hits:
            article_id = hit.chunk.source_article_id
            article_counts[article_id] = article_counts.get(article_id, 0) + 1
        if len(article_counts) > 10:
            raise ValueError("evidence packet may contain at most 10 unique articles")
        if any(count > 3 for count in article_counts.values()):
            raise ValueError("evidence packet may contain at most 3 chunks per article")
        _require_timezone(self.created_at, "created_at")
        return self


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
