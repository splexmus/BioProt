from __future__ import annotations

from dualrag.rag.schemas import GroundedProteinReport, ReportVerification


def render_markdown(report: GroundedProteinReport, verification: ReportVerification) -> str:
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
        "## Evidence-linked claims",
        "",
    ]
    for claim in report.claims:
        citations = ", ".join(f"`{item}`" for item in claim.evidence_ids) or "none"
        lines.append(
            f"- **{claim.claim_type} / {claim.inference_level}:** {claim.text} "
            f"(evidence: {citations})"
        )
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
