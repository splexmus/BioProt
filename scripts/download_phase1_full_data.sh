#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Download the recommended Phase 1 research data bundle.

Usage:
  scripts/download_phase1_full_data.sh --data-root PATH --yes [OPTIONS]

Options:
  --data-root PATH          Storage root (or set DUALRAG_DATA_ROOT).
  --components LIST        Comma-separated components. Default:
                           sifts,swissprot,eggnog-extras,uniref90
  --build-uniref-index     Build the standalone UniRef90 MMseqs2 database/index.
  --threads N              Threads for MMseqs2 indexing. Default: 8.
  --minimum-free-gb N      Abort below this free-space threshold. Default: 600.
  --download-only          Do not extract the eggNOG optional archives.
  --dry-run                Print planned downloads without network transfers.
  --yes                    Confirm the potentially large transfer.
  -h, --help               Show this help.

Components:
  sifts                    PDB-chain functional mappings from PDBe SIFTS.
  swissprot                Reviewed UniProtKB FASTA and annotations.
  eggnog-extras            eggNOG 5.0.2 MMseqs2 and Pfam packages.
  uniref90                 UniRef90 FASTA and release metadata.

The script is resumable. Downloads use .part files, gzip/tar validation, local
SHA-256 inventories, and an append-only provenance event log. Existing valid
archives are reused. It never downloads full AlphaFoldDB, TrEMBL, or PMC.
EOF
}

data_root=${DUALRAG_DATA_ROOT:-}
components=sifts,swissprot,eggnog-extras,uniref90
build_uniref_index=false
extract_eggnog=true
dry_run=false
confirmed=false
threads=8
minimum_free_gb=600

while (($#)); do
  case "$1" in
    --data-root)
      [[ $# -ge 2 ]] || { echo "error: --data-root requires a path" >&2; exit 2; }
      data_root=$2
      shift 2
      ;;
    --components)
      [[ $# -ge 2 ]] || { echo "error: --components requires a list" >&2; exit 2; }
      components=$2
      shift 2
      ;;
    --build-uniref-index)
      build_uniref_index=true
      shift
      ;;
    --threads)
      [[ $# -ge 2 ]] || { echo "error: --threads requires an integer" >&2; exit 2; }
      threads=$2
      shift 2
      ;;
    --minimum-free-gb)
      [[ $# -ge 2 ]] || { echo "error: --minimum-free-gb requires an integer" >&2; exit 2; }
      minimum_free_gb=$2
      shift 2
      ;;
    --download-only)
      extract_eggnog=false
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --yes)
      confirmed=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$data_root" ]] || {
  echo "error: pass --data-root PATH or set DUALRAG_DATA_ROOT" >&2
  exit 2
}
[[ "$threads" =~ ^[1-9][0-9]*$ ]] || { echo "error: --threads must be positive" >&2; exit 2; }
[[ "$minimum_free_gb" =~ ^[0-9]+$ ]] || {
  echo "error: --minimum-free-gb must be a non-negative integer" >&2
  exit 2
}
if [[ "$dry_run" != true && "$confirmed" != true ]]; then
  echo "error: pass --yes after reviewing --dry-run output" >&2
  exit 2
fi

declare -A selected=()
IFS=',' read -r -a requested_components <<< "$components"
for component in "${requested_components[@]}"; do
  case "$component" in
    sifts|swissprot|eggnog-extras|uniref90) selected["$component"]=1 ;;
    *) echo "error: unsupported component: $component" >&2; exit 2 ;;
  esac
done
if [[ "$build_uniref_index" == true && -z "${selected[uniref90]:-}" ]]; then
  echo "error: --build-uniref-index requires the uniref90 component" >&2
  exit 2
fi

for command_name in wget gzip tar sha256sum df awk date findmnt; do
  command -v "$command_name" >/dev/null || {
    echo "error: required command is unavailable: $command_name" >&2
    exit 1
  }
done
if [[ "$build_uniref_index" == true ]]; then
  command -v mmseqs >/dev/null || {
    echo "error: mmseqs is required with --build-uniref-index" >&2
    exit 1
  }
fi

mkdir -p "$data_root"
data_root=$(cd "$data_root" && pwd -P)
[[ -w "$data_root" ]] || { echo "error: data root is not writable: $data_root" >&2; exit 1; }

mount_options=$(findmnt -T "$data_root" -no OPTIONS 2>/dev/null || true)
if [[ ",$mount_options," == *,ro,* ]]; then
  echo "error: filesystem is mounted read-only: $data_root ($mount_options)" >&2
  exit 1
fi

available_kb=$(df -Pk "$data_root" | awk 'NR == 2 {print $4}')
required_kb=$((minimum_free_gb * 1024 * 1024))
if ((available_kb < required_kb)); then
  echo "error: only $((available_kb / 1024 / 1024)) GB free; require ${minimum_free_gb} GB" >&2
  exit 1
fi

lock_dir="$data_root/.phase1-full-download.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "error: another downloader may be active: $lock_dir" >&2
  exit 1
fi
cleanup() {
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

metadata_dir="$data_root/databases/metadata"
events_file="$metadata_dir/download-events.tsv"
mkdir -p "$metadata_dir"
if [[ ! -e "$events_file" ]]; then
  printf 'retrieved_at_utc\tcomponent\tsource_url\tlocal_path\tsha256\n' > "$events_file"
fi

validate_file() {
  local path=$1
  local logical_path=${path%.part}
  [[ -s "$path" ]] || { echo "error: empty download: $path" >&2; return 1; }
  case "$logical_path" in
    *.tar.gz|*.tgz) tar -tzf "$path" >/dev/null ;;
    *.gz) gzip -t "$path" ;;
  esac
}

record_event() {
  local component=$1
  local url=$2
  local path=$3
  local checksum
  checksum=$(sha256sum "$path" | awk '{print $1}')
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$component" "$url" "$path" "$checksum" \
    >> "$events_file"
}

download_file() {
  local component=$1
  local url=$2
  local destination=$3
  mkdir -p "$(dirname "$destination")"
  if [[ -s "$destination" ]]; then
    validate_file "$destination"
    echo "using existing verified file: $destination"
    return
  fi
  if [[ "$dry_run" == true ]]; then
    echo "would download: $url"
    echo "             -> $destination"
    return
  fi
  echo "downloading: $url"
  wget --continue --https-only --output-document "$destination.part" "$url"
  validate_file "$destination.part"
  mv "$destination.part" "$destination"
  record_event "$component" "$url" "$destination"
}

write_inventory() {
  local directory=$1
  shift
  local inventory="$directory/SHA256SUMS.local"
  if [[ "$dry_run" == true ]]; then
    echo "would write checksum inventory: $inventory"
    return
  fi
  local path
  : > "$inventory.tmp"
  for path in "$@"; do
    [[ -s "$path" ]] && sha256sum "$path" >> "$inventory.tmp"
  done
  mv "$inventory.tmp" "$inventory"
}

download_sifts() {
  local base=https://ftp.ebi.ac.uk/pub/databases/msd/sifts/flatfiles/tsv
  local directory="$metadata_dir/sifts"
  local names=(
    pdb_chain_uniprot.tsv.gz
    pdb_chain_go.tsv.gz
    pdb_chain_interpro.tsv.gz
    pdb_chain_pfam.tsv.gz
    pdb_chain_enzyme.tsv.gz
    pdb_chain_taxonomy.tsv.gz
    pdb_pubmed.tsv.gz
    pdb_chain_cath_uniprot.tsv.gz
    pdb_chain_scop2_uniprot.tsv.gz
    pdb_chain_scop2b_sf_uniprot.tsv.gz
  )
  local paths=()
  local name
  for name in "${names[@]}"; do
    download_file sifts "$base/$name" "$directory/$name"
    paths+=("$directory/$name")
  done
  write_inventory "$directory" "${paths[@]}"
}

download_swissprot() {
  local base=https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete
  local directory="$data_root/databases/uniprot/swissprot/current"
  local names=(reldate.txt RELEASE.metalink uniprot_sprot.fasta.gz uniprot_sprot.dat.gz)
  local paths=()
  local name
  for name in "${names[@]}"; do
    download_file swissprot "$base/$name" "$directory/$name"
    paths+=("$directory/$name")
  done
  write_inventory "$directory" "${paths[@]}"
}

safe_extract_tar() {
  local archive=$1
  local destination=$2
  if tar -tzf "$archive" | awk '
    /^\// || /(^|\/)\.\.($|\/)/ {unsafe=1}
    END {exit unsafe ? 1 : 0}
  '; then
    tar -xzf "$archive" -C "$destination"
  else
    echo "error: archive contains an unsafe path: $archive" >&2
    return 1
  fi
}

download_eggnog_extras() {
  local base=https://downloads.eggnogdb.org/emapper/emapperdb-5.0.2
  local directory="$data_root/databases/eggnog"
  local archive_dir="$directory/archives"
  local mmseqs_archive="$archive_dir/mmseqs.tar.gz"
  local pfam_archive="$archive_dir/pfam.tar.gz"
  download_file eggnog-extras "$base/mmseqs.tar.gz" "$mmseqs_archive"
  download_file eggnog-extras "$base/pfam.tar.gz" "$pfam_archive"
  write_inventory "$archive_dir" "$mmseqs_archive" "$pfam_archive"

  if [[ "$extract_eggnog" != true || "$dry_run" == true ]]; then
    [[ "$dry_run" == true ]] && echo "would extract eggNOG extras into: $directory"
    return
  fi
  if [[ ! -s "$directory/.mmseqs-5.0.2.installed" ]]; then
    [[ ! -e "$directory/mmseqs" ]] || {
      echo "error: $directory/mmseqs exists without an installation marker" >&2
      return 1
    }
    echo "extracting eggNOG MMseqs2 database"
    safe_extract_tar "$mmseqs_archive" "$directory"
    printf 'eggNOG 5.0.2\n' > "$directory/.mmseqs-5.0.2.installed"
  else
    echo "using installed eggNOG MMseqs2 database"
  fi
  if [[ ! -s "$directory/.pfam-5.0.2.installed" ]]; then
    [[ ! -e "$directory/pfam" ]] || {
      echo "error: $directory/pfam exists without an installation marker" >&2
      return 1
    }
    echo "extracting eggNOG Pfam database"
    safe_extract_tar "$pfam_archive" "$directory"
    printf 'eggNOG 5.0.2\n' > "$directory/.pfam-5.0.2.installed"
  else
    echo "using installed eggNOG Pfam database"
  fi
}

download_uniref90() {
  local base=https://ftp.uniprot.org/pub/databases/uniprot/current_release/uniref/uniref90
  local directory="$data_root/databases/mmseqs/uniref90/current"
  local names=(README RELEASE.metalink uniref90.release_note uniref90.fasta.gz)
  local paths=()
  local name
  for name in "${names[@]}"; do
    download_file uniref90 "$base/$name" "$directory/$name"
    paths+=("$directory/$name")
  done
  write_inventory "$directory" "${paths[@]}"

  if [[ "$build_uniref_index" != true ]]; then
    if [[ "$dry_run" == true ]]; then
      echo "would leave UniRef90 unindexed unless --build-uniref-index is supplied"
    else
      echo "UniRef90 FASTA downloaded; index creation was not requested"
    fi
    return
  fi
  if [[ "$dry_run" == true ]]; then
    echo "would build MMseqs2 database/index: $directory/uniref90_mmseqs"
    return
  fi
  local database="$directory/uniref90_mmseqs"
  local tmp_dir="$data_root/tmp/mmseqs-uniref90-index"
  mkdir -p "$tmp_dir"
  if [[ ! -s "$database.dbtype" ]]; then
    mmseqs createdb "$directory/uniref90.fasta.gz" "$database"
  fi
  if [[ ! -e "$database.idx" && ! -e "$database.idx.dbtype" ]]; then
    mmseqs createindex "$database" "$tmp_dir" --threads "$threads"
  else
    echo "using existing UniRef90 MMseqs2 index: $database"
  fi
}

echo "data root: $data_root"
echo "components: $components"
echo "free space: $((available_kb / 1024 / 1024)) GB"
[[ "$dry_run" == true ]] && echo "mode: dry run"

[[ -n "${selected[sifts]:-}" ]] && download_sifts
[[ -n "${selected[swissprot]:-}" ]] && download_swissprot
[[ -n "${selected[eggnog-extras]:-}" ]] && download_eggnog_extras
[[ -n "${selected[uniref90]:-}" ]] && download_uniref90

echo "Phase 1 data download completed for: $components"
echo "provenance log: $events_file"
