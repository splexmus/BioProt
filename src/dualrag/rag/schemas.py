from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RagModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InferenceLevel(StrEnum):
    DIRECT_EXPERIMENTAL_EVIDENCE = "DIRECT_EXPERIMENTAL_EVIDENCE"
    INDIRECT_HOMOLOG_EVIDENCE = "INDIRECT_HOMOLOG_EVIDENCE"
    COMPUTATIONAL_PREDICTION = "COMPUTATIONAL_PREDICTION"
    BACKGROUND_CONTEXT = "BACKGROUND_CONTEXT"
    ALTERNATIVE_HYPOTHESIS = "ALTERNATIVE_HYPOTHESIS"
    RECOMMENDED_EXPERIMENT = "RECOMMENDED_EXPERIMENT"


class ClaimType(StrEnum):
    FUNCTION = "FUNCTION"
    SEQUENCE = "SEQUENCE"
    STRUCTURE = "STRUCTURE"
    DOMAIN_ONTOLOGY = "DOMAIN_ONTOLOGY"
    LITERATURE = "LITERATURE"
    CONFLICT = "CONFLICT"
    LIMITATION = "LIMITATION"


class VerificationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class VerificationStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    REJECT_UNSUPPORTED_CLAIMS = "REJECT_UNSUPPORTED_CLAIMS"
    REJECT_INVALID_CITATIONS = "REJECT_INVALID_CITATIONS"
    REJECT_SCHEMA_FAILURE = "REJECT_SCHEMA_FAILURE"


class ContextEvidence(RagModel):
    evidence_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    details: dict[str, object] = Field(default_factory=dict)
    citation_id: str | None = None
    source_url: str | None = None
    assessed_role: str = "UNASSESSED"


class GenerationContext(RagModel):
    schema_version: int = 1
    context_version: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    query_accession: str | None = None
    protein_name: str | None = None
    organism: str | None = None
    cross_modal_status: str = Field(min_length=1)
    candidate_functions: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    evidence: list[ContextEvidence] = Field(default_factory=list)
    claim_boundaries: list[str] = Field(min_length=1)
    phase4_exit_status: str = Field(min_length=1)
    phase4_exit_override: bool = False
    confidence_status: Literal["NOT_CALIBRATED"] = "NOT_CALIBRATED"

    @model_validator(mode="after")
    def unique_evidence_ids(self) -> GenerationContext:
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("context evidence IDs must be unique")
        return self


class ReportClaim(RagModel):
    claim_id: str = Field(min_length=1)
    claim_type: ClaimType
    text: str = Field(min_length=1)
    inference_level: InferenceLevel
    evidence_ids: list[str] = Field(min_length=1)


class ReportReference(RagModel):
    evidence_id: str = Field(min_length=1)
    citation_id: str | None = None
    source_url: str | None = None


class GroundedProteinReport(RagModel):
    schema_version: int = 1
    report_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    proposed_function: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    confidence_status: Literal["NOT_CALIBRATED"] = "NOT_CALIBRATED"
    claims: list[ReportClaim] = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(min_length=1)
    validation_experiments: list[str] = Field(default_factory=list)
    references: list[ReportReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ids(self) -> GroundedProteinReport:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("report claim IDs must be unique")
        reference_ids = [reference.evidence_id for reference in self.references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("report reference evidence IDs must be unique")
        return self


class VerificationFinding(RagModel):
    code: str = Field(min_length=1)
    severity: VerificationSeverity
    message: str = Field(min_length=1)
    claim_id: str | None = None
    evidence_id: str | None = None


class ReportVerification(RagModel):
    schema_version: int = 1
    report_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    status: VerificationStatus
    findings: list[VerificationFinding] = Field(default_factory=list)
    checked_at: datetime
    verifier_version: str = Field(min_length=1)


class GenerationRecord(RagModel):
    schema_version: int = 1
    query_id: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    ollama_version: str | None = None
    prompt_version: str = Field(min_length=1)
    context_sha256: str = Field(min_length=1)
    raw_response_sha256: str = Field(min_length=1)
    generated_at: datetime
    temperature: float
    seed: int
    phase4_exit_override: bool
    verification_status: VerificationStatus
