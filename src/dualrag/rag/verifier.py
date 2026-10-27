from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from dualrag.rag.schemas import (
    ContextEvidence,
    GenerationContext,
    GroundedProteinReport,
    InferenceLevel,
    ReportVerification,
    VerificationFinding,
    VerificationSeverity,
    VerificationStatus,
)

VERIFIER_VERSION = "deterministic-report-verifier-v2"
_CONTROLLED_ID = re.compile(
    r"\b(?:GO:\d{7}|EC:\d+(?:\.[\d-]+){1,3}|IPR\d{6}|PF\d{5}|[A-NR-Z][0-9][A-Z0-9]{3}[0-9])\b"
)
_OVERCLAIM = re.compile(
    r"\b(?:experimentally confirmed|experimentally validated|proves?|definitively|certainly)\b",
    re.IGNORECASE,
)


def verify_report(report: GroundedProteinReport, context: GenerationContext) -> ReportVerification:
    findings: list[VerificationFinding] = []
    evidence = {item.evidence_id: item for item in context.evidence}
    references = {item.evidence_id: item for item in report.references}
    invalid_citation = False
    unsupported = False

    if report.proposed_function not in context.candidate_functions:
        unsupported = True
        findings.append(
            VerificationFinding(
                code="FUNCTION_OUTSIDE_CANDIDATES",
                severity=VerificationSeverity.ERROR,
                message="Proposed function is absent from supplied candidate functions.",
            )
        )

    matching_candidate_ids = {
        item.evidence_id
        for item in context.evidence
        if item.evidence_type == "COMPUTATIONAL_CANDIDATE"
        and item.label == report.proposed_function
    }
    grounded_function_claim = any(
        claim.claim_type.value == "FUNCTION"
        and claim.inference_level is InferenceLevel.COMPUTATIONAL_PREDICTION
        and bool(set(claim.evidence_ids) & matching_candidate_ids)
        for claim in report.claims
    )
    if not grounded_function_claim:
        unsupported = True
        findings.append(
            VerificationFinding(
                code="FUNCTION_WITHOUT_MATCHING_CANDIDATE_CLAIM",
                severity=VerificationSeverity.ERROR,
                message=(
                    "Proposed function lacks a COMPUTATIONAL_PREDICTION function claim "
                    "citing its matching candidate evidence."
                ),
            )
        )

    for claim in report.claims:
        if not claim.evidence_ids:
            unsupported = True
            findings.append(
                VerificationFinding(
                    code="CLAIM_WITHOUT_EVIDENCE",
                    severity=VerificationSeverity.ERROR,
                    claim_id=claim.claim_id,
                    message="Scientific claim has no supplied evidence ID.",
                )
            )

        for evidence_id in claim.evidence_ids:
            item = evidence.get(evidence_id)
            if item is None:
                invalid_citation = True
                findings.append(
                    VerificationFinding(
                        code="UNKNOWN_EVIDENCE_ID",
                        severity=VerificationSeverity.ERROR,
                        claim_id=claim.claim_id,
                        evidence_id=evidence_id,
                        message="Claim cites an evidence ID absent from the context.",
                    )
                )
                continue
            if evidence_id not in references:
                invalid_citation = True
                findings.append(
                    VerificationFinding(
                        code="MISSING_REFERENCE_ENTRY",
                        severity=VerificationSeverity.ERROR,
                        claim_id=claim.claim_id,
                        evidence_id=evidence_id,
                        message="Claim evidence is missing from the report reference list.",
                    )
                )
            if (
                item.evidence_type == "LITERATURE"
                and item.assessed_role == "UNASSESSED"
                and claim.inference_level is not InferenceLevel.BACKGROUND_CONTEXT
            ):
                unsupported = True
                findings.append(
                    VerificationFinding(
                        code="UNASSESSED_LITERATURE_OUTSIDE_BACKGROUND",
                        severity=VerificationSeverity.ERROR,
                        claim_id=claim.claim_id,
                        evidence_id=evidence_id,
                        message="UNASSESSED literature may be used only as background context.",
                    )
                )
        if claim.inference_level is InferenceLevel.COMPUTATIONAL_PREDICTION and _OVERCLAIM.search(
            claim.text
        ):
            unsupported = True
            findings.append(
                VerificationFinding(
                    code="COMPUTATIONAL_OVERCLAIM",
                    severity=VerificationSeverity.ERROR,
                    claim_id=claim.claim_id,
                    message="Computational prediction is phrased as experimental certainty.",
                )
            )

    _check_modality_discussion(
        evidence=evidence,
        report=report,
        evidence_type="SEQUENCE_RETRIEVAL_HIT",
        claim_type="SEQUENCE",
        finding_code="SEQUENCE_SUPPORT_NOT_DISCUSSED",
        findings=findings,
    )
    _check_modality_discussion(
        evidence=evidence,
        report=report,
        evidence_type="STRUCTURE_RETRIEVAL_HIT",
        claim_type="STRUCTURE",
        finding_code="STRUCTURE_SUPPORT_NOT_DISCUSSED",
        findings=findings,
    )

    for evidence_id, reference in references.items():
        item = evidence.get(evidence_id)
        if item is None:
            invalid_citation = True
            findings.append(
                VerificationFinding(
                    code="UNKNOWN_REFERENCE_ID",
                    severity=VerificationSeverity.ERROR,
                    evidence_id=evidence_id,
                    message="Reference points outside the supplied evidence packet.",
                )
            )
            continue
        if reference.citation_id != item.citation_id or reference.source_url != item.source_url:
            invalid_citation = True
            findings.append(
                VerificationFinding(
                    code="REFERENCE_METADATA_MISMATCH",
                    severity=VerificationSeverity.ERROR,
                    evidence_id=evidence_id,
                    message="Reference identifier or URL differs from supplied evidence.",
                )
            )

    context_text = json.dumps(context.model_dump(mode="json"), sort_keys=True)
    report_text = json.dumps(report.model_dump(mode="json"), sort_keys=True)
    context_ids = set(_CONTROLLED_ID.findall(context_text))
    for identifier in sorted(set(_CONTROLLED_ID.findall(report_text)) - context_ids):
        unsupported = True
        findings.append(
            VerificationFinding(
                code="UNSUPPLIED_CONTROLLED_IDENTIFIER",
                severity=VerificationSeverity.ERROR,
                message=f"Report introduced controlled identifier {identifier}.",
            )
        )

    if context.phase4_exit_override:
        findings.append(
            VerificationFinding(
                code="PHASE4_EXIT_BYPASSED",
                severity=VerificationSeverity.WARNING,
                message="Report used an explicit unvalidated Phase 4 override.",
            )
        )
    if invalid_citation:
        status = VerificationStatus.REJECT_INVALID_CITATIONS
    elif unsupported:
        status = VerificationStatus.REJECT_UNSUPPORTED_CLAIMS
    elif findings:
        status = VerificationStatus.PASS_WITH_WARNINGS
    else:
        status = VerificationStatus.PASS
    return ReportVerification(
        report_id=report.report_id,
        query_id=report.query_id,
        status=status,
        findings=findings,
        checked_at=datetime.now(UTC),
        verifier_version=VERIFIER_VERSION,
    )


def _check_modality_discussion(
    *,
    evidence: dict[str, ContextEvidence],
    report: GroundedProteinReport,
    evidence_type: str,
    claim_type: str,
    finding_code: str,
    findings: list[VerificationFinding],
) -> None:
    modality_ids = {
        evidence_id
        for evidence_id, item in evidence.items()
        if item.evidence_type == evidence_type
    }
    if not modality_ids:
        return
    discussed = any(
        claim.claim_type.value == claim_type and bool(set(claim.evidence_ids) & modality_ids)
        for claim in report.claims
    )
    if not discussed:
        findings.append(
            VerificationFinding(
                code=finding_code,
                severity=VerificationSeverity.WARNING,
                message=(
                    f"Context contains {evidence_type} records, but the generated report "
                    f"has no evidence-linked {claim_type} claim."
                ),
            )
        )
