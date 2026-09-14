# DATA.md — Databases, Storage, Caching, and Provenance

## Principles
1. Large databases do not live in Git.
2. Large databases do not live inside Conda environments.
3. External SSD/HPC/shared storage is the default for local eggNOG and Foldseek databases.
4. Raw downloads are immutable where practical; derived indexes are reproducible artifacts.
5. Every result records the database/version/source that produced it.

## Expected sources

| Evidence | Primary source/tool |
|---|---|
| Protein sequence | UniProt / project FASTA |
| Orthology/function | eggNOG-mapper / eggNOG |
| Sequence similarity | MMseqs2; optional HMMER/BLAST/DIAMOND |
| Predicted query structure | AlphaFold DB REST API plus bounded local cache |
| Experimental structure | PDB |
| Structure search | Foldseek |
| Domains/families | InterPro/Pfam/SUPFAM where available |
| Ontology/function | GO / EC / pathway annotations |
| Literature | PubMed / PMC |

## AlphaFold policy
Do not mirror AlphaFoldDB for the standard project workflow. Store eggNOG and Foldseek
target databases locally, but retrieve AlphaFold query models on demand through the
AlphaFold DB REST API.

Preferred strategy:

```text
UniProt accession
  -> AlphaFold DB REST metadata lookup
  -> download one required PDB/mmCIF model
  -> checksum + acquisition manifest + bounded cache
  -> local Foldseek search against a local versioned database
```

For ordinary and batch experiments, use an accession-keyed cache instead of mirroring
the source database. Maintain a manifest with lookup status, accession, API endpoint,
model version/source, download timestamp, checksum, and local path. Define cache
retention separately from preservation of published-run artifacts.

## Proposed storage tree

```text
$DUALRAG_DATA_ROOT/
├── databases/
│   ├── eggnog/
│   ├── foldseek/
│   ├── mmseqs/
│   └── metadata/
├── structures/
│   ├── alphafold/        # on-demand query-model cache only
│   └── pdb/
├── literature/
│   ├── raw/
│   ├── parsed/
│   └── indexes/
├── datasets/
│   ├── raw/
│   ├── curated/
│   └── manifests/
├── experiments/
├── results/
└── tmp/
```

## Database manifest
Keep a machine-readable manifest, e.g. `databases/metadata/databases.yaml`:

```yaml
eggnog:
  version: null
  downloaded_at: null
  path: databases/eggnog
  notes: "Fill after installation"
foldseek_pdb:
  version: null
  downloaded_at: null
  path: databases/foldseek/pdb
  notes: "Fill after database creation/download"
alphafold_api:
  base_url: https://alphafold.ebi.ac.uk/api
  accessed_at: null
  notes: "Remote query-model source; not a locally mirrored database"
```

Never invent version fields; leave null until verified.

## Git ignore policy
Suggested patterns:

```gitignore
.env
*.log
__pycache__/
.pytest_cache/
.ruff_cache/

# Data and databases
/data/
/databases/
/structures/
/literature_cache/
/indexes/
/tmp/
/results/
/experiments/

# Large bioinformatics artifacts
*.pdb
*.cif
*.mmcif
*.a3m
*.hhr
*.ffdata
*.ffindex
```

If small fixtures are needed for tests, store them under `tests/fixtures/` and keep them intentionally tiny.

## Storage estimate
Practical planning range for this project: **250–600 GB** active use.

The on-demand AlphaFold cache reduces predicted-structure storage, but local eggNOG
and Foldseek databases and indexes still dominate capacity planning.

Recommended device:
- 2 TB external SSD for normal multi-organism research
- 4 TB SSD for larger repeated experiments
- HPC/shared storage for metagenomic/proteome-scale expansion

Reserve substantial free space for Foldseek/MMseqs2 temporary work and index construction.

## Data provenance fields
Every normalized row should be traceable through fields such as:

```text
source_database
source_database_version
source_accession
tool
tool_version
parameters_hash
run_id
retrieved_at
raw_output_path
```

## Deletion/cache policy
Safe to regenerate/delete:
- temporary files
- derived vector indexes when source text and embedding model are versioned
- intermediate normalized caches if raw outputs and code version are preserved

Preserve:
- curated benchmark manifests
- gold labels and provenance
- raw tool outputs for published benchmark runs
- exact configs and software/database version metadata
