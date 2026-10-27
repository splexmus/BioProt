#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_phase6_calibration.sh [options]

Options:
  --data-root DIR    default: /media/splexmus/4TB_HDD1/dualrag
  --run-name NAME    default: phase6-development-v1
  --phase3-run DIR   default: benchmark/phase3-pipeline-v2-conservative
  --dataset DIR      default: benchmark/phase3-pilot-v1

Fits on the development split, evaluates on validation, and excludes the exposed test split.
The runner refuses to overwrite an existing calibration run.
EOF
}

data_root="${DUALRAG_DATA_ROOT:-/media/splexmus/4TB_HDD1/dualrag}"
run_name="phase6-development-v1"
phase3_run="benchmark/phase3-pipeline-v2-conservative"
dataset="benchmark/phase3-pilot-v1"
while (($#)); do
  case "$1" in
    --data-root) data_root="$2"; shift 2 ;;
    --run-name) run_name="$2"; shift 2 ;;
    --phase3-run) phase3_run="$2"; shift 2 ;;
    --dataset) dataset="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$data_root" = /* ]] || { echo "--data-root must be absolute" >&2; exit 2; }
[[ "$run_name" != */* && "$run_name" != *..* ]] || { echo "unsafe --run-name" >&2; exit 2; }
output="$data_root/calibration/runs/$run_name"
[[ ! -e "$output" ]] || { echo "Refusing to overwrite existing run: $output" >&2; exit 1; }

pixi run python -m dualrag calibrate-confidence \
  --predictions "$phase3_run/predictions.tsv" \
  --candidates "$phase3_run/ablation_candidates.tsv" \
  --gold-labels "$dataset/gold_labels.tsv" \
  --splits "$dataset/splits.tsv" \
  --difficulty "$dataset/difficulty_strata.tsv" \
  --contract config/calibration-contract-v1.yaml \
  --output "$output"
