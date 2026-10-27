from __future__ import annotations

from dualrag.rag.schemas import (
    ContextEvidence,
    GenerationContext,
    GroundedProteinReport,
    ReportClaim,
    ReportVerification,
)

RENDERER_VERSION = "phase5-markdown-v2"


def render_markdown(
    report: GroundedProteinReport,
    verification: ReportVerification,
    context: GenerationContext | None = None,
) -> str:
    lines = [
        f"# {report.title}",
        "",
        f"- Query: `{report.query_id}`",
        f"- Confidence: `{report.confidence_status}`",
        f"- Verification: `{verification.status}`",
        "",
        "## Putative function",
        "",
        report.proposed_function,
        "",
        report.summary,
        "",
    ]
    remaining_claims = list(report.claims)
    if context is not None:
        sequence = [
            item for item in context.evidence if item.evidence_type == "SEQUENCE_RETRIEVAL_HIT"
        ]
        structure = [
            item for item in context.evidence if item.evidence_type == "STRUCTURE_RETRIEVAL_HIT"
        ]
        sequence_ids = {item.evidence_id for item in sequence}
        structure_ids = {item.evidence_id for item in structure}
        sequence_claims = _claims_for_modality(
            remaining_claims, include=sequence_ids, exclude=structure_ids
        )
        structure_claims = _claims_for_modality(
            remaining_claims, include=structure_ids, exclude=sequence_ids
        )
        cross_modal_claims = [
            claim
            for claim in remaining_claims
            if set(claim.evidence_ids) & sequence_ids
            and set(claim.evidence_ids) & structure_ids
        ]
        assigned = {
            id(claim)
            for claim in [*sequence_claims, *structure_claims, *cross_modal_claims]
        }
        remaining_claims = [claim for claim in remaining_claims if id(claim) not in assigned]
        _retrieval_section(lines, "Sequence retrieval support", sequence, sequence_claims)
        _retrieval_section(lines, "Structure retrieval support", structure, structure_claims)
        lines.extend(["", "## Cross-modal interpretation", ""])
        lines.append(f"- Cross-modal status: `{context.cross_modal_status}`")
        _claim_list(lines, cross_modal_claims, empty="No generated cross-modal claim reported.")

    lines.extend(["", "## Other evidence-linked claims", ""])
    _claim_list(lines, remaining_claims, empty="No additional evidence-linked claims reported.")
    _section(lines, "Alternatives", report.alternatives)
    _section(lines, "Conflicts", report.conflicts)
    _section(lines, "Uncertainty", report.uncertainty)
    _section(lines, "Recommended validation experiments", report.validation_experiments)
    lines.extend(["", "## References", ""])
    for reference in report.references:
        label = reference.citation_id or reference.evidence_id
        if reference.source_url:
            lines.append(f"- [{label}]({reference.source_url}) — `{reference.evidence_id}`")
        else:
            lines.append(f"- {label} — `{reference.evidence_id}`")
    if verification.findings:
        lines.extend(["", "## Verification findings", ""])
        for finding in verification.findings:
            lines.append(f"- `{finding.severity}` `{finding.code}`: {finding.message}")
    lines.extend(
        [
            "",
            "> This is a putative research hypothesis, not experimental confirmation.",
            "",
        ]
    )
    return "\n".join(lines)


def _section(lines: list[str], title: str, values: list[str]) -> None:
    lines.extend(["", f"## {title}", ""])
    lines.extend(f"- {value}" for value in values)
    if not values:
        lines.append("- None reported.")


def _claims_for_modality(
    claims: list[ReportClaim], *, include: set[str], exclude: set[str]
) -> list[ReportClaim]:
    return [
        claim
        for claim in claims
        if set(claim.evidence_ids) & include and not set(claim.evidence_ids) & exclude
    ]


def _claim_list(lines: list[str], claims: list[ReportClaim], *, empty: str) -> None:
    if not claims:
        lines.append(f"- {empty}")
        return
    for claim in claims:
        citations = ", ".join(f"`{item}`" for item in claim.evidence_ids) or "none"
        lines.append(
            f"- **{claim.claim_type} / {claim.inference_level}:** {claim.text} "
            f"(evidence: {citations})"
        )


def _retrieval_section(
    lines: list[str], title: str, evidence: list[ContextEvidence], claims: list[ReportClaim]
) -> None:
    lines.extend(["", f"## {title}", ""])
    if not evidence:
        lines.append("- No allowed retrieval records were available for this modality.")
    for item in evidence:
        details = item.details
        target = details.get("target_id") or item.evidence_id
        rank = details.get("rank", "unknown")
        score = _format_value(details.get("score"))
        lines.extend(
            [
                f"### Rank {rank}: {item.label}",
                "",
                f"- Evidence ID: `{item.evidence_id}`",
                f"- Target: `{target}`",
                f"- Normalized ranking score: `{score}`",
            ]
        )
        metrics = details.get("raw_metrics", {})
        if isinstance(metrics, dict) and metrics:
            rendered = "; ".join(
                f"{key}={_format_value(value)}" for key, value in metrics.items()
            )
            lines.append(f"- Raw metrics: {rendered}")
        annotations = details.get("annotations", {})
        if isinstance(annotations, dict) and annotations:
            for namespace, values in annotations.items():
                rendered_values = ", ".join(f"`{value}`" for value in values)
                lines.append(f"- {namespace}: {rendered_values}")
        provenance = " | ".join(
            str(value)
            for value in (
                details.get("tool"),
                details.get("tool_version"),
                details.get("database"),
                details.get("database_version"),
            )
            if value is not None
        )
        if provenance:
            lines.append(f"- Provenance: {provenance}")
        if details.get("structure_source") is not None:
            lines.append(f"- Structure source: `{details['structure_source']}`")
        if details.get("experimental_structure") is not None:
            lines.append(
                f"- Experimental target structure: "
                f"`{str(details['experimental_structure']).lower()}`"
            )
        lines.append("")
    lines.extend(["### Evidence-linked interpretation", ""])
    _claim_list(
        lines,
        claims,
        empty=(
            "No generated modality-specific claim reported; the retrieval records above "
            "remain available for direct review."
        ),
    )


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
