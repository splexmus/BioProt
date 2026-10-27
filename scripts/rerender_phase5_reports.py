from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl
from dualrag.rag.render import RENDERER_VERSION, render_markdown
from dualrag.rag.schemas import GenerationContext, GroundedProteinReport, ReportVerification


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render existing Phase 5 JSON reports with separated evidence sections."
    )
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run = args.run.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    reports_path = run / "generated_reports.jsonl"
    verifications_path = run / "report_verifications.jsonl"
    reports = read_jsonl(reports_path, GroundedProteinReport)
    verifications = {
        item.query_id: item for item in read_jsonl(verifications_path, ReportVerification)
    }
    output.mkdir(parents=True)
    for report in reports:
        context_path = run / "contexts" / f"{report.query_id}.json"
        context = GenerationContext.model_validate(
            json.loads(context_path.read_text(encoding="utf-8"))
        )
        verification = verifications[report.query_id]
        (output / f"{report.query_id}.md").write_text(
            render_markdown(report, verification, context), encoding="utf-8"
        )
    manifest = {
        "schema_version": 1,
        "renderer_version": RENDERER_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source_run": str(run),
        "report_count": len(reports),
        "inputs": {
            "generated_reports": file_sha256(reports_path),
            "report_verifications": file_sha256(verifications_path),
        },
        "outputs": {
            path.name: file_sha256(path)
            for path in sorted(output.glob("*.md"))
        },
    }
    write_json(output / "render_manifest.json", manifest)
    print(f"rendered {len(reports)} reports -> {output}")


if __name__ == "__main__":
    main()
