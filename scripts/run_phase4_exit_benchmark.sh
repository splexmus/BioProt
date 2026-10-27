#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_phase4_exit_benchmark.sh prepare --email ADDRESS [options]
  scripts/run_phase4_exit_benchmark.sh evaluate [options]

Options:
  --data-root DIR   default: /media/splexmus/4TB_HDD1/dualrag
  --run-name NAME   default: phase4-exit-development-v1
  --email ADDRESS   required for prepare
  --queries N       development queries, minimum 20 (default: 20)

prepare builds leakage-safe Phase 4 queries from Phase 3 development records, runs
PubMed/PMC acquisition, preserves the full candidate pool, and creates a blank pooled
annotation TSV. evaluate requires that every pool row has been manually annotated and
applies the thresholds frozen in config/literature-evaluation-v2.yaml.
EOF
}

action="${1:-}"
[[ "$action" == "prepare" || "$action" == "evaluate" ]] || { usage >&2; exit 2; }
shift
email=""
data_root="${DUALRAG_DATA_ROOT:-/media/splexmus/4TB_HDD1/dualrag}"
run_name="phase4-exit-development-v1"
query_count=20
while (($#)); do
  case "$1" in
    --email) email="$2"; shift 2 ;;
    --data-root) data_root="$2"; shift 2 ;;
    --run-name) run_name="$2"; shift 2 ;;
    --queries) query_count="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$data_root" = /* ]] || { echo "--data-root must be absolute" >&2; exit 2; }
[[ "$run_name" != */* && "$run_name" != *..* ]] || { echo "unsafe --run-name" >&2; exit 2; }
((query_count >= 20)) || { echo "--queries must be at least 20" >&2; exit 2; }
mount_info="$(findmnt -T "$data_root" -n -o SOURCE,TARGET,FSTYPE,OPTIONS 2>/dev/null || true)"
[[ -n "$mount_info" ]] || { echo "No filesystem resolves $data_root" >&2; exit 1; }
read -r mount_source mount_target mount_type mount_options <<<"$mount_info"
echo "Storage: source=$mount_source target=$mount_target type=$mount_type options=$mount_options"
[[ ",$mount_options," != *,ro,* ]] || { echo "HDD is read-only" >&2; exit 1; }
[[ -w "$mount_target" ]] || { echo "HDD is not writable by this user" >&2; exit 1; }

run_dir="$data_root/literature/runs/$run_name"
query_dir="$run_dir/queries"
if [[ "$action" == "prepare" ]]; then
  [[ -n "$email" ]] || { echo "--email is required for prepare" >&2; exit 2; }
  if [[ -z "${NCBI_API_KEY:-}" ]]; then
    echo "NCBI_API_KEY is not set; continuing at the adapter's conservative unauthenticated rate" >&2
  fi
  [[ ! -e "$run_dir" ]] || {
    echo "Refusing to overwrite existing run: $run_dir" >&2
    exit 1
  }
  mkdir -p "$query_dir"
  pixi run python -m dualrag build-literature-benchmark-queries \
    --dataset benchmark/phase3-pilot-v1 \
    --phase3-run benchmark/phase3-pipeline-v2-conservative \
    --output "$query_dir" \
    --split development \
    --maximum-queries "$query_count" \
    --go-obo benchmark/phase3-mappings-v1/sources/go-basic.obo \
    --ec2go benchmark/phase3-mappings-v1/sources/ec2go
  pixi run python -m dualrag run-literature \
    --queries "$query_dir/literature_queries.jsonl" \
    --output "$run_dir" \
    --email "$email" \
    --retmax 50 \
    --candidate-pool 100 \
    --top-k 20
  pixi run python -m dualrag make-literature-label-template \
    --candidates "$run_dir/literature_candidates.jsonl" \
    --output "$run_dir/manual_pool_labels.tsv"
  pixi run python scripts/finalize_phase4_exit.py --run "$run_dir" --stage prepared
  echo "Prepared candidate pool. Human annotation required:"
  echo "  $run_dir/manual_pool_labels.tsv"
  exit 0
fi

labels="$run_dir/manual_pool_labels.tsv"
[[ -f "$labels" ]] || { echo "Missing manual labels: $labels" >&2; exit 1; }
pixi run python -m dualrag evaluate-literature \
  --hits "$run_dir/literature_hits.jsonl" \
  --candidates "$run_dir/literature_candidates.jsonl" \
  --queries "$query_dir/literature_queries.jsonl" \
  --labels "$labels" \
  --acceptance config/literature-evaluation-v2.yaml \
  --output "$run_dir/evaluation"
pixi run python scripts/finalize_phase4_exit.py --run "$run_dir" --stage evaluated
jq '{status, acceptance, metrics, method_metrics}' "$run_dir/evaluation/literature_evaluation.json"
