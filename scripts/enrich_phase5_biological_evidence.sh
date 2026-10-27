#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/enrich_phase5_biological_evidence.sh [options]

Options:
  --data-root DIR       default: /media/splexmus/4TB_HDD1/dualrag
  --phase4-run NAME     default: phase4-exit-development-v4
  --phase3-run DIR      default: benchmark/phase3-pipeline-v2-conservative
  --max-per-modality N  default: 5; maximum: 5

Writes evidence_packets.biological-v1.jsonl and its manifest inside the Phase 4 run.
The script refuses to overwrite either artifact.
EOF
}

data_root="${DUALRAG_DATA_ROOT:-/media/splexmus/4TB_HDD1/dualrag}"
phase4_run="phase4-exit-development-v4"
phase3_run="benchmark/phase3-pipeline-v2-conservative"
max_per_modality=5
while (($#)); do
  case "$1" in
    --data-root) data_root="$2"; shift 2 ;;
    --phase4-run) phase4_run="$2"; shift 2 ;;
    --phase3-run) phase3_run="$2"; shift 2 ;;
    --max-per-modality) max_per_modality="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$data_root" = /* ]] || { echo "--data-root must be absolute" >&2; exit 2; }
[[ "$phase4_run" != */* && "$phase4_run" != *..* ]] || { echo "unsafe --phase4-run" >&2; exit 2; }
[[ "$max_per_modality" =~ ^[1-5]$ ]] || { echo "--max-per-modality must be 1..5" >&2; exit 2; }

phase4_dir="$data_root/literature/runs/$phase4_run"
packets="$phase4_dir/evidence_packets.jsonl"
output="$phase4_dir/evidence_packets.biological-v1.jsonl"
manifest="$phase4_dir/evidence_packets.biological-v1.manifest.json"
sequence="$phase3_run/raw/sequence_evidence.tsv"
structure="$phase3_run/raw/structure_evidence.tsv"
source_manifest="$phase3_run/reproducibility_manifest.json"

for required in "$packets" "$sequence" "$structure" "$source_manifest"; do
  [[ -f "$required" ]] || { echo "Missing required input: $required" >&2; exit 1; }
done
[[ ! -e "$output" && ! -e "$manifest" ]] || {
  echo "Refusing to overwrite existing Phase 5.1 artifacts" >&2
  exit 1
}

pixi run python -m dualrag enrich-phase5-evidence \
  --packets "$packets" \
  --sequence-evidence "$sequence" \
  --structure-evidence "$structure" \
  --source-manifest "$source_manifest" \
  --max-per-modality "$max_per_modality" \
  --output "$output" \
  --manifest "$manifest"
