#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_phase4_on_hdd.sh --queries FILE --email ADDRESS [options]

Options:
  --data-root DIR      HDD DualRAG root (default: /media/splexmus/4TB_HDD1/dualrag)
  --run-name NAME      Output subdirectory (default: phase4-YYYYmmdd-HHMMSS)
  --api-key-env NAME   Environment variable holding the NCBI key (default: NCBI_API_KEY)
  --retmax N           PubMed hits per query variant (default: 50)
  --candidate-pool N   Unique PMIDs retained per protein (default: 100)
  --top-k N            Final passages per protein, maximum 20 (default: 20)
  --skip-pmc           Retrieve PubMed abstracts only
  --dry-run            Validate paths and print the command without network access

The script never falls back to the repository or internal disk. Raw responses,
normalized records, chunks, hits, packets, manifests, and label templates are written
under DATA_ROOT/literature/runs/RUN_NAME.
EOF
}

queries=""
email=""
data_root="${DUALRAG_DATA_ROOT:-/media/splexmus/4TB_HDD1/dualrag}"
run_name="phase4-$(date -u +%Y%m%d-%H%M%S)"
api_key_env="NCBI_API_KEY"
retmax=50
candidate_pool=100
top_k=20
skip_pmc=0
dry_run=0

while (($#)); do
  case "$1" in
    --queries) queries="$2"; shift 2 ;;
    --email) email="$2"; shift 2 ;;
    --data-root) data_root="$2"; shift 2 ;;
    --run-name) run_name="$2"; shift 2 ;;
    --api-key-env) api_key_env="$2"; shift 2 ;;
    --retmax) retmax="$2"; shift 2 ;;
    --candidate-pool) candidate_pool="$2"; shift 2 ;;
    --top-k) top_k="$2"; shift 2 ;;
    --skip-pmc) skip_pmc=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$queries" && -f "$queries" ]] || { echo "--queries must name an existing file" >&2; exit 2; }
[[ -n "$email" ]] || { echo "--email is required by NCBI policy" >&2; exit 2; }
[[ "$data_root" = /* ]] || { echo "--data-root must be absolute" >&2; exit 2; }
[[ "$run_name" != */* && "$run_name" != *..* ]] || { echo "unsafe --run-name" >&2; exit 2; }
if [[ -n "${!api_key_env-}" ]]; then
  echo "NCBI API key: configured via $api_key_env (value not displayed)"
else
  echo "NCBI API key: not set in this shell; conservative unauthenticated pacing will be used"
fi

mount_info="$(findmnt -T "$data_root" -n -o SOURCE,TARGET,FSTYPE,OPTIONS 2>/dev/null || true)"
if [[ -z "$mount_info" ]]; then
  echo "No mounted filesystem resolves $data_root" >&2
  exit 1
fi
read -r mount_source mount_target mount_type mount_options <<<"$mount_info"
echo "Storage: source=$mount_source target=$mount_target type=$mount_type options=$mount_options"
if [[ "$mount_target" != "/media/splexmus/4TB_HDD1" ]]; then
  echo "Refusing internal-disk fallback: expected mount target /media/splexmus/4TB_HDD1" >&2
  exit 1
fi
if [[ ",$mount_options," == *,ro,* ]]; then
  cat >&2 <<EOF
The HDD is mounted read-only, so no Phase 4 data was written.
Because the mount reports errors=remount-ro, inspect the kernel/filesystem state first:
  findmnt -T "$data_root" -o SOURCE,TARGET,FSTYPE,OPTIONS,SIZE,AVAIL
  dmesg --level=err,warn | tail -n 80

After safely repairing/remounting the filesystem outside this script, verify:
  test -w "$mount_target" && echo writable

Then rerun this same command. Do not use sudo to run the pipeline itself.
EOF
  exit 1
fi
[[ -w "$mount_target" ]] || { echo "Mount is not writable by the current user: $mount_target" >&2; exit 1; }

output="$data_root/literature/runs/$run_name"
command=(pixi run python -m dualrag run-literature
  --queries "$queries"
  --output "$output"
  --email "$email"
  --api-key-env "$api_key_env"
  --retmax "$retmax"
  --candidate-pool "$candidate_pool"
  --top-k "$top_k")
((skip_pmc)) && command+=(--skip-pmc)

printf 'Output: %s\nCommand:' "$output"
printf ' %q' "${command[@]}"
printf '\n'
((dry_run)) && exit 0

mkdir -p "$output"
"${command[@]}"
pixi run python -m dualrag make-literature-label-template \
  --candidates "$output/literature_candidates.jsonl" \
  --output "$output/manual_labels.tsv"

echo "Phase 4.3-4.6 artifacts: $output"
echo "Next: manually annotate $output/manual_labels.tsv, then run:"
printf 'pixi run python -m dualrag evaluate-literature --hits %q --labels %q --output %q\n' \
  "$output/literature_hits.jsonl" "$output/manual_labels.tsv" "$output/evaluation"
