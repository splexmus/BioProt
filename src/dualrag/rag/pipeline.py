from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, stable_hash, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import EvidencePacket
from dualrag.rag.context import build_generation_context
from dualrag.rag.ollama import OllamaClient
from dualrag.rag.render import render_markdown
from dualrag.rag.schemas import GenerationRecord, GroundedProteinReport, ReportVerification
from dualrag.rag.verifier import verify_report

GENERATION_PIPELINE_VERSION = "phase5-ollama-generation-v1"
PROMPT_VERSION = "phase5-grounded-report-v1"


def run_generation_pipeline(
    *,
    packets_path: Path,
    output_dir: Path,
    client: OllamaClient,
    system_prompt_path: Path,
    report_prompt_path: Path,
    allow_unvalidated_phase4: bool = False,
    query_ids: set[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    packets = read_jsonl(packets_path, EvidencePacket)
    if query_ids is not None:
        packets = [packet for packet in packets if packet.query.query_id in query_ids]
        missing = sorted(query_ids - {packet.query.query_id for packet in packets})
        if missing:
            raise ValueError(f"requested query IDs are absent from packets: {missing}")
    if limit is not None:
        packets = packets[:limit]
    if not packets:
        raise ValueError("no evidence packets selected for generation")

    phase4_status = _phase4_exit_status(packets_path.parent)
    if phase4_status != "PASS" and not allow_unvalidated_phase4:
        raise ValueError(
            f"Phase 4 exit status is {phase4_status!r}; pass "
            "allow_unvalidated_phase4=True only for explicitly experimental generation"
        )

    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    report_prompt = report_prompt_path.read_text(encoding="utf-8")
    ollama_version = client.version()
    available_models = client.models()
    if not _model_available(client.config.model, available_models):
        raise ValueError(
            f"Ollama model {client.config.model!r} is not installed; available={available_models}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    contexts_dir = output_dir / "contexts"
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    contexts_dir.mkdir(exist_ok=True)
    raw_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    reports: list[GroundedProteinReport] = []
    verifications: list[ReportVerification] = []
    records: list[GenerationRecord] = []

    for packet in packets:
        query_id = packet.query.query_id
        context = build_generation_context(
            packet,
            phase4_exit_status=phase4_status,
            phase4_exit_override=phase4_status != "PASS",
        )
        context_path = contexts_dir / f"{query_id}.json"
        write_json(context_path, context.model_dump(mode="json"))
        report, raw_response = client.generate_report(
            context=context,
            system_prompt=system_prompt,
            report_prompt=report_prompt,
        )
        raw_path = raw_dir / f"{query_id}.json"
        write_json(raw_path, raw_response)
        verification = verify_report(report, context)
        report_path = reports_dir / f"{query_id}.json"
        markdown_path = reports_dir / f"{query_id}.md"
        write_json(report_path, report.model_dump(mode="json"))
        markdown_path.write_text(render_markdown(report, verification), encoding="utf-8")
        reports.append(report)
        verifications.append(verification)
        records.append(
            GenerationRecord(
                query_id=query_id,
                packet_id=packet.packet_id,
                model=client.config.model,
                ollama_version=ollama_version,
                prompt_version=PROMPT_VERSION,
                context_sha256=file_sha256(context_path),
                raw_response_sha256=file_sha256(raw_path),
                generated_at=datetime.now(UTC),
                temperature=client.config.temperature,
                seed=client.config.seed,
                phase4_exit_override=phase4_status != "PASS",
                verification_status=verification.status,
            )
        )

    write_jsonl(output_dir / "generated_reports.jsonl", reports)
    write_jsonl(output_dir / "report_verifications.jsonl", verifications)
    write_jsonl(output_dir / "generation_records.jsonl", records)
    status_counts = Counter(str(item.status) for item in verifications)
    manifest = {
        "schema_version": 1,
        "pipeline_version": GENERATION_PIPELINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "model": client.config.model,
        "ollama_version": ollama_version,
        "temperature": client.config.temperature,
        "seed": client.config.seed,
        "report_count": len(reports),
        "verification_status_counts": dict(sorted(status_counts.items())),
        "phase4_exit_status": phase4_status,
        "phase4_exit_override": phase4_status != "PASS",
        "scientific_status": (
            "EXPERIMENTAL_UNVALIDATED_PHASE4_OVERRIDE"
            if phase4_status != "PASS"
            else "EXPERIMENTAL_PHASE5_GENERATION"
        ),
        "inputs": {
            "packets": file_sha256(packets_path),
            "system_prompt": file_sha256(system_prompt_path),
            "report_prompt": file_sha256(report_prompt_path),
        },
        "outputs": {
            name: file_sha256(output_dir / name)
            for name in (
                "generated_reports.jsonl",
                "report_verifications.jsonl",
                "generation_records.jsonl",
            )
        },
        "limitations": [
            "Deterministic verification checks evidence links and claim boundaries; it does "
            "not establish semantic truth.",
            "Confidence is NOT_CALIBRATED until Phase 6.",
            "Generated reports are putative hypotheses, not experimental confirmation.",
        ],
        "parameters_hash": stable_hash(
            {
                "model": client.config.model,
                "temperature": client.config.temperature,
                "seed": client.config.seed,
                "prompt_version": PROMPT_VERSION,
            }
        ),
    }
    manifest.update(_runtime_provenance(output_dir))
    write_json(output_dir / "generation_manifest.json", manifest)
    return manifest


def _phase4_exit_status(run_dir: Path) -> str:
    path = run_dir / "phase4_exit_manifest.json"
    if not path.is_file():
        return "NOT_EVALUATED"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    evaluation = manifest.get("evaluation")
    if isinstance(evaluation, dict):
        direct = evaluation.get("status")
        if direct:
            return str(direct)
        acceptance = evaluation.get("acceptance")
        if isinstance(acceptance, dict) and acceptance.get("status"):
            return str(acceptance["status"])
    return "NOT_EVALUATED"


def _model_available(requested: str, available: list[str]) -> bool:
    normalized = {item.removesuffix(":latest") for item in available}
    return requested.removesuffix(":latest") in normalized


def augment_generation_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "generation_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"generation manifest is missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(_runtime_provenance(run_dir))
    write_json(path, manifest)
    return manifest


def _runtime_provenance(output_dir: Path) -> dict[str, Any]:
    lock = Path("pixi.lock")
    artifacts = {
        str(path.relative_to(output_dir)): file_sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "generation_manifest.json"
    }
    return {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pixi_lock_sha256": file_sha256(lock) if lock.is_file() else None,
        },
        "git": {
            "commit": _git(["rev-parse", "HEAD"]),
            "status": _git(["status", "--short"]),
        },
        "artifact_checksums": artifacts,
    }


def _git(arguments: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else None
