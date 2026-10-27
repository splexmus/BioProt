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


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:11434"
    model: str = "gemma3:4b"
    timeout_seconds: float = Field(default=300.0, gt=0)
    temperature: float = Field(default=0.0, ge=0)
    seed: int = 42


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
            "format": output_schema,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.config.temperature,
                "seed": self.config.seed,
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
            raise ValueError("Ollama response has no message.content JSON")
        report = GroundedProteinReport.model_validate_json(content)
        if report.query_id != context.query_id:
            raise ValueError(
                f"Ollama report query_id {report.query_id!r} does not match "
                f"context {context.query_id!r}"
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
        if "COMPUTATIONAL_CANDIDATE" in types:
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
    return report.model_copy(update={"claims": claims})
