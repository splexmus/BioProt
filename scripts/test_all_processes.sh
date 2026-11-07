#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/test_all_processes.sh

Runs the complete safe offline engineering test without network access, HDD writes,
Ollama, large biological databases, or sealed test labels. Expensive/scientific stages
are listed as manual checks at the end.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
[[ $# -eq 0 ]] || { usage >&2; exit 2; }
[[ -f pixi.toml && -f config/config.yaml ]] || {
  echo "Run this script from the BioProt repository root." >&2
  exit 2
}
command -v pixi >/dev/null || {
  echo "pixi is required. Install Pixi, then run: pixi install --locked" >&2
  exit 1
}

work_dir="$(mktemp -d /tmp/dualrag-all-processes.XXXXXX)"
cleanup() {
  [[ "$work_dir" == /tmp/dualrag-all-processes.* ]] && rm -rf -- "$work_dir"
}
trap cleanup EXIT

step() { printf '\n[%s] %s\n' "$1" "$2"; }

step "1/7" "Unit tests"
pixi run pytest -q

step "2/7" "Formatting and static checks"
pixi run ruff check src tests

step "3/7" "CLI and external-tool diagnostics"
pixi run python -m dualrag --help >/dev/null
pixi run python -m dualrag check-tools

step "4/7" "Offline Phase 1-2 dual-retrieval fixture"
for run in first second; do
  pixi run python -m dualrag run \
    --config config/config.yaml \
    --input tests/fixtures/queries.fasta \
    --output "$work_dir/$run"
done

step "5/7" "Reproducibility comparison"
pixi run python -m dualrag compare-runs \
  --first "$work_dir/first" \
  --second "$work_dir/second" \
  --output "$work_dir/reproducibility.json"

step "6/7" "Phase 4 leakage-safe query construction"
pixi run python -m dualrag build-literature-queries \
  --run "$work_dir/first" \
  --output "$work_dir/literature-queries" \
  --context tests/fixtures/literature_query_context.tsv

step "7/7" "Phase runner interfaces"
bash -n scripts/run_phase4_on_hdd.sh
bash -n scripts/run_phase5_ollama.sh
bash -n scripts/run_phase6_calibration.sh
scripts/run_phase4_on_hdd.sh --help >/dev/null
scripts/run_phase5_ollama.sh init --help >/dev/null
scripts/run_phase6_calibration.sh --help >/dev/null

cat <<'EOF'

SAFE OFFLINE TEST: PASS

Covered:
  PASS  Python unit and contract tests, including the literature vector index
  PASS  Ruff static checks
  PASS  CLI loading and tool diagnostics
  PASS  Phase 1 sequence/structure fixture retrieval
  PASS  Phase 2 normalization, fusion, conflict, and audit outputs
  PASS  Repeat-run reproducibility
  PASS  Phase 4 query construction
  PASS  Phase 4-6 runner syntax and help interfaces

Not executed automatically:
  MANUAL  Real eggNOG/MMseqs2, AlphaFold API, and Foldseek database search
  MANUAL  Phase 3 scientific benchmark or any sealed test labels
  MANUAL  PubMed/PMC network acquisition and human literature labels
  MANUAL  Ollama Phase 5 report generation and expert review
  MANUAL  Phase 6 calibration or frozen validation
  FUTURE  Phase 7 GraphRAG
  PILOT   Phase 8 uncharacterized-protein study

See docs/TESTING_ALL_PROCESSES.md for the manual commands and interpretation rules.
EOF
