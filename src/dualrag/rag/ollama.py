from __future__ import annotations

import json
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field

from dualrag.rag.schemas import (
    ClaimType,
    GenerationContext,
    GroundedProteinReport,
    InferenceLevel,
    ReportClaim,
    ReportReference,
)

DEFAULT_OLLAMA_MODEL = "gemma4:more"


class OllamaResponseError(ValueError):
    """An Ollama response that could not satisfy the report contract."""

    def __init__(self, message: str, raw_response: dict[str, Any]):
        super().__init__(message)
        self.raw_response = raw_response


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:11434"
    model: str = DEFAULT_OLLAMA_MODEL
    timeout_seconds: float = Field(default=300.0, gt=0)
    temperature: float = Field(default=0.0, ge=0)
    seed: int = 42
    num_predict: int = Field(default=8192, gt=0)
    think: bool = False


class OllamaClient:
    def __init__(self, config: OllamaConfig, session: Any | None = None):
        self.config = config
        self.session = session or requests.Session()

    def version(self) -> str:
        response = self.session.get(
            f"{self.config.base_url.rstrip('/')}/api/version",
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return str(response.json().get("version", "unknown"))

    def models(self) -> list[str]:
        response = self.session.get(
            f"{self.config.base_url.rstrip('/')}/api/tags",
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return [str(item["name"]) for item in response.json().get("models", [])]

    def pull(self) -> dict[str, Any]:
        response = self.session.post(
            f"{self.config.base_url.rstrip('/')}/api/pull",
            json={"model": self.config.model, "stream": False},
            timeout=max(self.config.timeout_seconds, 3600),
        )
        response.raise_for_status()
        return dict(response.json())

    def generate_report(
        self,
        *,
        context: GenerationContext,
        system_prompt: str,
        report_prompt: str,
    ) -> tuple[GroundedProteinReport, dict[str, Any]]:
        context_json = json.dumps(
            context.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
        )
        user_prompt = report_prompt.replace("{context_json}", context_json)
        output_schema = _contextual_output_schema(context)
        payload = {
            "model": self.config.model,
            "stream": False,
            "think": self.config.think,
            "format": output_schema,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.config.temperature,
                "seed": self.config.seed,
                "num_predict": self.config.num_predict,
            },
        }
        response = self.session.post(
            f"{self.config.base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        raw = dict(response.json())
        content = raw.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError("Ollama response has no message.content JSON", raw)
        try:
            report = GroundedProteinReport.model_validate_json(content)
        except ValueError as exc:
            raise OllamaResponseError("Ollama response failed report validation", raw) from exc
        if report.query_id != context.query_id:
            raise OllamaResponseError(
                f"Ollama report query_id {report.query_id!r} does not match "
                f"context {context.query_id!r}",
                raw,
            )
        report = _canonicalize_claim_roles(report, context)
        evidence = {item.evidence_id: item for item in context.evidence}
        cited_ids = list(
            dict.fromkeys(
                evidence_id
                for claim in report.claims
                for evidence_id in claim.evidence_ids
                if evidence_id in evidence
            )
        )
        report = report.model_copy(
            update={
                "report_id": f"report:{context.query_id}",
                "references": [
                    ReportReference(
                        evidence_id=evidence_id,
                        citation_id=evidence[evidence_id].citation_id,
                        source_url=evidence[evidence_id].source_url,
                    )
                    for evidence_id in cited_ids
                ],
            }
        )
        return report, raw


def _contextual_output_schema(context: GenerationContext) -> dict[str, Any]:
    schema = GroundedProteinReport.model_json_schema()
    schema["properties"]["query_id"]["enum"] = [context.query_id]
    allowed_functions = context.candidate_functions or ["INSUFFICIENT_EVIDENCE"]
    schema["properties"]["proposed_function"]["enum"] = allowed_functions
    evidence_ids = [item.evidence_id for item in context.evidence]
    schema["$defs"]["ReportClaim"]["properties"]["evidence_ids"]["items"]["enum"] = evidence_ids
    schema["$defs"]["ReportReference"]["properties"]["evidence_id"]["enum"] = evidence_ids
    if context.phase4_exit_override:
        schema["$defs"]["InferenceLevel"]["enum"] = [
            "INDIRECT_HOMOLOG_EVIDENCE",
            "COMPUTATIONAL_PREDICTION",
            "BACKGROUND_CONTEXT",
            "ALTERNATIVE_HYPOTHESIS",
        ]
    return schema


def _canonicalize_claim_roles(
    report: GroundedProteinReport, context: GenerationContext
) -> GroundedProteinReport:
    evidence = {item.evidence_id: item for item in context.evidence}
    claims: list[ReportClaim] = []
    for claim in report.claims:
        types = {
            evidence[evidence_id].evidence_type
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence
        }
        if types & {
            "COMPUTATIONAL_CANDIDATE",
            "SEQUENCE_RETRIEVAL_HIT",
            "STRUCTURE_RETRIEVAL_HIT",
            "DOMAIN_ONTOLOGY",
        }:
            level = InferenceLevel.COMPUTATIONAL_PREDICTION
        elif "SEQUENCE_HOMOLOG" in types:
            level = InferenceLevel.INDIRECT_HOMOLOG_EVIDENCE
        elif types == {"LITERATURE"}:
            level = InferenceLevel.BACKGROUND_CONTEXT
        else:
            level = claim.inference_level
        claims.append(claim.model_copy(update={"inference_level": level}))

    matching = next(
        (
            item
            for item in context.evidence
            if item.evidence_type == "COMPUTATIONAL_CANDIDATE"
            and item.label == report.proposed_function
        ),
        None,
    )
    has_function_claim = bool(
        matching
        and any(
            claim.claim_type is ClaimType.FUNCTION and matching.evidence_id in claim.evidence_ids
            for claim in claims
        )
    )
    if matching and not has_function_claim:
        claims.insert(
            0,
            ReportClaim(
                claim_id="system:function-candidate",
                claim_type=ClaimType.FUNCTION,
                text=(
                    f"The retrieval pipeline proposes {report.proposed_function} as a "
                    "putative function."
                ),
                inference_level=InferenceLevel.COMPUTATIONAL_PREDICTION,
                evidence_ids=[matching.evidence_id],
            ),
        )
    claims.extend(_missing_modality_claims(claims, context))
    return report.model_copy(update={"claims": claims})


def _missing_modality_claims(
    claims: list[ReportClaim], context: GenerationContext
) -> list[ReportClaim]:
    additions: list[ReportClaim] = []
    specifications = (
        ("SEQUENCE_RETRIEVAL_HIT", ClaimType.SEQUENCE, "sequence"),
        ("STRUCTURE_RETRIEVAL_HIT", ClaimType.STRUCTURE, "structure"),
    )
    for evidence_type, claim_type, modality in specifications:
        records = [item for item in context.evidence if item.evidence_type == evidence_type]
        if not records:
            continue
        record_ids = {item.evidence_id for item in records}
        if any(
            claim.claim_type is claim_type and bool(set(claim.evidence_ids) & record_ids)
            for claim in claims
        ):
            continue
        top = min(records, key=lambda item: int(item.details.get("rank", 10**9)))
        metrics = top.details.get("raw_metrics", {})
        metric_text = _modality_metric_text(modality, metrics)
        target = top.details.get("target_id", top.evidence_id)
        transfer_note = (
            "Functional transfer from this sequence match remains computational."
            if modality == "sequence"
            else "Structural similarity does not by itself establish identical function."
        )
        additions.append(
            ReportClaim(
                claim_id=f"system:{modality}-top-hit",
                claim_type=claim_type,
                text=(
                    f"The top {modality} retrieval hit is {top.label} ({target})"
                    f"{metric_text}. {transfer_note}"
                ),
                inference_level=InferenceLevel.COMPUTATIONAL_PREDICTION,
                evidence_ids=[top.evidence_id],
            )
        )
    return additions


def _modality_metric_text(modality: str, metrics: object) -> str:
    if not isinstance(metrics, dict):
        return ""
    fields = (
        ("sequence_identity", "identity"),
        ("alignment_coverage", "coverage"),
    ) if modality == "sequence" else (
        ("tm_score", "TM-score"),
        ("query_coverage", "query coverage"),
        ("target_coverage", "target coverage"),
    )
    rendered = [
        f"{label}={_short_number(metrics[key])}"
        for key, label in fields
        if metrics.get(key) is not None
    ]
    return f" with {', '.join(rendered)}" if rendered else ""


def _short_number(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)
