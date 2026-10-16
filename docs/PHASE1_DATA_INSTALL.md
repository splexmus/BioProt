# Phase 1 data installation on 4TB_HDD

This guide installs the Phase 1 databases under:

```text
/media/splexmus/4TB_HDD1/dualrag
```

The drive currently provides about 3.6 TB of usable space. Treat 2 TB as a soft
project budget, leaving the remaining capacity free for filesystem headroom and other
uses. Phase 1 does **not** mirror AlphaFoldDB: it downloads query models individually
through the AlphaFold REST API and caches them locally.

## 1. Confirm that the drive is writable

Run:

```bash
findmnt -T /media/splexmus/4TB_HDD1 -o SOURCE,FSTYPE,OPTIONS
df -h /media/splexmus/4TB_HDD1
```

The mount options must include `rw`. Stop if they include `ro`. Do not force-write an
NTFS filesystem. Safely eject/reconnect it first; if it remains read-only, repair it
from Windows with Fast Startup/hibernation disabled and a normal filesystem check.

The ext4 drive was observed as `ro,errors=remount-ro` on 2026-10-08, but the verified
database installation described below subsequently completed. Before any new download
or index build, recheck the current mount state; never run `fsck` on a mounted filesystem.

## 2. Initialize the non-destructive layout

From the repository root:

```bash
pixi run python -m dualrag init-storage \
  --config config/4tb-hdd.yaml
```

This creates directories, `databases/metadata/databases.yaml`, and an empty
`databases/foldseek/pdb_metadata.tsv`. It does not overwrite either metadata file.

For the shell commands below, define explicit quoted paths because the mount name
contains a space:

```bash
export DUALRAG_DATA_ROOT=/media/splexmus/4TB_HDD1/dualrag
export EGGNOG_DATA_DIR="$DUALRAG_DATA_ROOT/databases/eggnog"
export DUALRAG_FOLDSEEK_DB="$DUALRAG_DATA_ROOT/databases/foldseek/pdb"
export DUALRAG_TMP="$DUALRAG_DATA_ROOT/tmp"
export DUALRAG_RESULTS="$DUALRAG_DATA_ROOT/results"
```

## 3. Install the eggNOG data

eggNOG-mapper 2.1.13 uses a retired download hostname and can leave zero-byte `.gz`
files while still printing `Finished`. Upgrade to the final v2 release, which retains
eggNOG v5 compatibility:

eggNOG-mapper 2.1.15 is pinned by `pixi.toml` and `pixi.lock`. Install the project
environment before downloading data:

```bash
pixi install --locked
```

The currently available Bioconda 2.1.15 build was observed still carrying the old URL,
despite the upstream fix. Confirm that the mapper expects database version `5.0.2`, then
use the repository's resumable installer against the official HTTPS download index:

```bash
pixi run emapper.py --version
pixi run bash scripts/install_eggnog_v5.sh "$EGGNOG_DATA_DIR"
```

This installs and validates the annotation, taxonomy, and DIAMOND databases required by
the configured `diamond` search mode. Downloads use `.part` files, resume with `wget`,
pass `gzip -t` before promotion, and retain local SHA-256 checksums. Optional MMseqs2,
Pfam, novel-family, and HMM databases are deliberately excluded from the first run.

The installer safely replaces same-named zero-byte archives after a complete `.part`
download. To audit the failed artifacts first:

```bash
find "$EGGNOG_DATA_DIR" -maxdepth 1 -type f -size 0 -print
```

The version-matched files are published at the official
[eggNOG 5.0.2 download index](https://downloads.eggnogdb.org/emapper/emapperdb-5.0.2/).
As of 2026-10-08 it lists approximately 6 GB for `eggnog.db.gz`, 69 MB for the taxonomy
archive, and 5 GB for `eggnog_proteins.dmnd.gz`.

eggNOG-mapper 2.1.15 declares DIAMOND `>=2.0.11,<2.1`; this repository therefore pins
DIAMOND 2.0.15 rather than 2.1.x.

Verify the installed files and capture the reported versions:

```bash
test -s "$EGGNOG_DATA_DIR/eggnog.db"
test -s "$EGGNOG_DATA_DIR/eggnog_proteins.dmnd"
EGGNOG_DATA_DIR="$EGGNOG_DATA_DIR" pixi run emapper.py --version
du -sh "$EGGNOG_DATA_DIR"
```

## 4. Install the local Foldseek PDB target database

Use Foldseek's database downloader. PDB is the local search target; AlphaFold REST is
only the query-model source.

```bash
mkdir -p "$DUALRAG_TMP/foldseek-pdb"
pixi run foldseek databases \
  PDB \
  "$DUALRAG_FOLDSEEK_DB" \
  "$DUALRAG_TMP/foldseek-pdb" \
  --threads 8
```

The downloader may be rerun after an interrupted transfer. Do not delete its temporary
directory until validation succeeds.

Verify the database:

```bash
test -s "${DUALRAG_FOLDSEEK_DB}.dbtype"
test -s "${DUALRAG_FOLDSEEK_DB}.lookup"
pixi run foldseek version
du -sh "$DUALRAG_DATA_ROOT/databases/foldseek"
```

The official Foldseek command is documented as `foldseek databases PDB pdb tmp` in the
[Foldseek repository](https://github.com/steineggerlab/foldseek#databases).

## 5. Add PDB target metadata

Foldseek similarity output does not itself provide protein function. Populate
`$DUALRAG_DATA_ROOT/databases/foldseek/pdb_metadata.tsv` from a versioned PDB/SIFTS and
UniProt mapping workflow. The required header is created by `init-storage`:

```text
target_structure_id  target_uniprot_id  protein_name  interpro_ids  supfam_ids  structure_source  experimental_structure  source_accession
```

Use tab separators, semicolons for multiple identifiers, `PDB` as `structure_source`,
and `true` for `experimental_structure`. Target identifiers must exactly match Foldseek's
output identifiers. Record mapping source URLs, release dates, and checksums in the
database manifest. Until this table is populated, structural similarities are valid but
function-level agreement will usually remain uninformative.

After the SIFTS and Swiss-Prot files from section 8 are present, build the table with:

```bash
pixi run python -m dualrag.structure.metadata \
  --data-root "$DUALRAG_DATA_ROOT" \
  --work-dir "$DUALRAG_TMP"
```

The builder reads the exact target names from `pdb.lookup`, maps their PDB entry and
chain through SIFTS, and adds reviewed protein names from Swiss-Prot. It emits one row
for every unique Foldseek target, including unmapped targets, so missing metadata
remains visible rather than silently shrinking the search database. Duplicate lookup
names are collapsed deterministically and counted in the manifest. Repeated biological-
assembly copies such as `A-2` fall back to the SIFTS annotation for chain `A`.

`supfam_ids` remains empty because the downloaded bundle does not contain a SUPFAM
mapping; SCOP2 domain identifiers are not relabelled as SUPFAM identifiers. The builder
also writes `pdb_metadata.tsv.manifest.json` with input/output SHA-256 checksums, SIFTS
release headers, row counts, and annotation coverage. It stages joins in a temporary
SQLite database under `--work-dir`, then atomically replaces the output table.

## 6. Finalize provenance

Edit both `config/4tb-hdd.yaml` and
`$DUALRAG_DATA_ROOT/databases/metadata/databases.yaml` only after inspecting actual
installed versions. Replace `UNVERIFIED` with the observed eggNOG and PDB snapshot
versions/dates. Never invent a version from today's date.

For the verified installation described by this repository, the complete replacement
manifest is `config/databases.4tb-hdd.yaml`. Install it only when the paths and database
files match the current machine:

```bash
cp config/databases.4tb-hdd.yaml \
  "$DUALRAG_DATA_ROOT/databases/metadata/databases.yaml"
```

Record an inventory:

```bash
find "$DUALRAG_DATA_ROOT/databases" -maxdepth 2 -type f \
  -printf '%p\t%s bytes\n' | sort \
  > "$DUALRAG_DATA_ROOT/databases/metadata/file_inventory.tsv"
df -h /media/splexmus/4TB_HDD1
```

## 7. Run validation and a characterized-protein smoke test

Repository checks:

```bash
pixi run validate
```

Then run a small FASTA whose identifiers are validated UniProt accessions and whose
sequences exactly match those accessions:

```bash
pixi run python -m dualrag run \
  --config config/4tb-hdd.yaml \
  --input proteins.fasta \
  --output "$DUALRAG_RESULTS/phase1-smoke"
```

Inspect `alphafold_acquisition.tsv`, both modality result tables, `merged_results.tsv`,
`commands.log`, and `run_metadata.json`. A passing fixture test is not evidence that the
real database integration passed.

The repository includes a five-protein reviewed Swiss-Prot integration set and a
source-derived manifest:

```bash
pixi run python -m dualrag run \
  --config config/4tb-hdd.yaml \
  --input tests/fixtures/phase1_characterized.fasta \
  --output "$DUALRAG_RESULTS/phase1-characterized"
```

The corresponding `tests/fixtures/phase1_characterized_manifest.tsv` contains source
release, taxonomy, representative functional identifiers, sequence lengths, and
sequence SHA-256 values. It is an integration fixture, not a research benchmark.

Repeat the run into a second output directory, then compare stable results:

```bash
pixi run python -m dualrag compare-runs \
  --first "$DUALRAG_RESULTS/phase1-characterized-run1" \
  --second "$DUALRAG_RESULTS/phase1-characterized-run2" \
  --output "$DUALRAG_RESULTS/phase1-reproducibility.json"
```

The command exits nonzero if any stable biological or provenance field differs. It
allows cache-state and output-path differences and parallel cross-query block ordering,
but preserves within-query hit order.

## 8. Download the recommended full Phase 1 bundle

The repository provides a resumable downloader for the remaining recommended data:
PDBe SIFTS mappings, reviewed UniProtKB/Swiss-Prot annotations, the eggNOG 5.0.2
MMseqs2 and Pfam packages, and UniRef90. It deliberately excludes full AlphaFoldDB,
TrEMBL, and literature mirrors.

Review the transfer first:

```bash
scripts/download_phase1_full_data.sh \
  --data-root "$DUALRAG_DATA_ROOT" \
  --dry-run
```

Then start the resumable download and install the eggNOG extras:

```bash
scripts/download_phase1_full_data.sh \
  --data-root "$DUALRAG_DATA_ROOT" \
  --threads 8 \
  --yes
```

The script requires at least 600 GB free by default, validates gzip/tar archives before
promotion, retains partial downloads as `.part` files for resumption, writes local
SHA-256 inventories, and appends acquisition records to
`databases/metadata/download-events.tsv`.

The standalone UniRef90 MMseqs2 index is opt-in because it can consume hundreds of
gigabytes and the current Phase 1 adapter does not use that independent target yet:

```bash
pixi run bash scripts/download_phase1_full_data.sh \
  --data-root "$DUALRAG_DATA_ROOT" \
  --components uniref90 \
  --build-uniref-index \
  --threads 8 \
  --yes
```

To download a smaller stage independently, pass for example
`--components sifts,swissprot`. Existing valid files are reused; the script will not
silently replace them.

## Space and safety policy

- Keep at least 15% of the filesystem free during downloads and indexing.
- Preserve raw tool outputs and published-run artifacts.
- Temporary directories may be cleared only after the producing run has finished.
- Do not install databases inside the Pixi environment or Git repository.
- Do not download a local AlphaFoldDB mirror for this project.
- Do not label AlphaFold query models as experimental structures.
