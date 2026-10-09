#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 DATA_DIR" >&2
  exit 2
fi

data_dir=$1
base_url=https://downloads.eggnogdb.org/emapper/emapperdb-5.0.2

mkdir -p "$data_dir"
if [[ ! -w "$data_dir" ]]; then
  echo "error: eggNOG data directory is not writable: $data_dir" >&2
  exit 1
fi

download() {
  local name=$1
  local archive="$data_dir/$name"
  if [[ -s "$archive" ]]; then
    gzip -t "$archive"
    echo "using existing non-empty archive: $archive"
    return
  fi
  echo "downloading $name"
  wget --continue --https-only --output-document "$archive.part" "$base_url/$name"
  gzip -t "$archive.part"
  mv -f "$archive.part" "$archive"
}

download eggnog.db.gz
download eggnog.taxa.tar.gz
download eggnog_proteins.dmnd.gz

echo "computing SHA-256 checksums for approximately 12 GB of archives"
sha256sum \
  "$data_dir/eggnog.db.gz" \
  "$data_dir/eggnog.taxa.tar.gz" \
  "$data_dir/eggnog_proteins.dmnd.gz" \
  > "$data_dir/SHA256SUMS.local"

if [[ ! -s "$data_dir/eggnog.db" ]]; then
  echo "extracting eggnog.db (this expands to approximately 41 GB)"
  gzip -dc "$data_dir/eggnog.db.gz" > "$data_dir/eggnog.db.tmp"
  mv "$data_dir/eggnog.db.tmp" "$data_dir/eggnog.db"
fi

if [[ ! -s "$data_dir/eggnog.taxa.db" ]]; then
  echo "extracting eggNOG taxonomy database"
  tar -xzf "$data_dir/eggnog.taxa.tar.gz" -C "$data_dir"
fi

if [[ ! -s "$data_dir/eggnog_proteins.dmnd" ]]; then
  echo "extracting eggNOG DIAMOND database"
  gzip -dc "$data_dir/eggnog_proteins.dmnd.gz" > "$data_dir/eggnog_proteins.dmnd.tmp"
  mv "$data_dir/eggnog_proteins.dmnd.tmp" "$data_dir/eggnog_proteins.dmnd"
fi

echo "running SQLite quick_check over the 41 GB annotation database; this can be quiet for minutes"
python - "$data_dir/eggnog.db" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
result = connection.execute("PRAGMA quick_check").fetchone()
connection.close()
if result != ("ok",):
    raise SystemExit(f"SQLite quick_check failed for {path}: {result}")
print(f"SQLite quick_check: ok ({path})")
PY

echo "validating the DIAMOND database"
diamond dbinfo --db "$data_dir/eggnog_proteins.dmnd"
echo "eggNOG 5.0.2 core data installed at $data_dir"
