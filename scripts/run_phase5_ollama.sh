#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_phase5_ollama.sh init [--model MODEL]
  scripts/run_phase5_ollama.sh smoke [options]
  scripts/run_phase5_ollama.sh run [options]

Options:
  --data-root DIR       default: /media/splexmus/4TB_HDD1/dualrag
  --phase4-run NAME     default: phase4-exit-development-v4
  --run-name NAME       default: phase5-ollama-development-v1
  --packets FILE        optional explicit packet file; otherwise prefer biological-v1
  --model MODEL         default: gemma3:4b
  --query-id ID         smoke default: first packet
  --base-url URL        default: http://127.0.0.1:11434

The v4 run passes the separate Phase 5 development transition, but its scientific Phase 4
exit is still FAIL. This workflow records the required scientific-gate override in every
context and manifest. Start `ollama serve` first if no service is active.
EOF
}

action="${1:-}"
[[ "$action" == "init" || "$action" == "smoke" || "$action" == "run" ]] || {
  usage >&2
  exit 2
}
shift
data_root="${DUALRAG_DATA_ROOT:-/media/splexmus/4TB_HDD1/dualrag}"
phase4_run="phase4-exit-development-v4"
run_name="phase5-ollama-development-v1"
model="gemma3:4b"
query_id=""
base_url="http://127.0.0.1:11434"
packets_override=""
while (($#)); do
  case "$1" in
    --data-root) data_root="$2"; shift 2 ;;
    --phase4-run) phase4_run="$2"; shift 2 ;;
    --run-name) run_name="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    --query-id) query_id="$2"; shift 2 ;;
    --base-url) base_url="$2"; shift 2 ;;
    --packets) packets_override="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ "$action" == "init" ]]; then
  pixi run python -m dualrag init-ollama --model "$model" --base-url "$base_url" --pull
  exit 0
fi

[[ "$data_root" = /* ]] || { echo "--data-root must be absolute" >&2; exit 2; }
[[ "$phase4_run" != */* && "$phase4_run" != *..* ]] || { echo "unsafe --phase4-run" >&2; exit 2; }
[[ "$run_name" != */* && "$run_name" != *..* ]] || { echo "unsafe --run-name" >&2; exit 2; }
phase4_dir="$data_root/literature/runs/$phase4_run"
if [[ -n "$packets_override" ]]; then
  packets="$packets_override"
elif [[ -f "$phase4_dir/evidence_packets.biological-v1.jsonl" ]]; then
  packets="$phase4_dir/evidence_packets.biological-v1.jsonl"
else
  packets="$phase4_dir/evidence_packets.jsonl"
fi
[[ -f "$packets" ]] || { echo "Missing evidence packets: $packets" >&2; exit 1; }
echo "Phase 5 evidence packets: $packets"

if [[ "$action" == "smoke" ]]; then
  output="$data_root/rag/runs/${run_name}-smoke"
  args=(--limit 1)
  if [[ -n "$query_id" ]]; then
    args=(--query-id "$query_id")
  fi
else
  output="$data_root/rag/runs/$run_name"
  args=()
fi
[[ ! -e "$output" ]] || { echo "Refusing to overwrite existing run: $output" >&2; exit 1; }

pixi run python -m dualrag generate-reports \
  --packets "$packets" \
  --output "$output" \
  --model "$model" \
  --base-url "$base_url" \
  --allow-unvalidated-phase4 \
  "${args[@]}"
