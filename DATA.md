# DATA.md — Databases, Storage, Caching, and Provenance

## Principles
1. Large databases do not live in Git.
2. Large databases do not live inside Pixi/Conda environments.
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

Phase 3 pins independent GO mapping resources separately from benchmark gold labels:
InterPro2GO, EC2GO, and `go-basic.obo`. PDB-chain GO/EC/InterPro and UniProt resolution
come from the same SIFTS release used to build Foldseek target metadata. Mapping
projections are annotation rules, not experimental evidence or identifier equivalence.

The production Foldseek target metadata schema includes chain-level `go_terms` and
`ec_numbers` in addition to UniProt, protein name, and InterPro. Old metadata tables
without GO/EC can execute structure search but materially reduce function retrieval.
Rebuild them with `python -m dualrag.structure.metadata`; the atomic output and manifest
record annotation coverage and checksums. Missing target annotations stay explicit.

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

## Fusion mapping policy

Cross-namespace mappings and curated label synonyms are small, versioned scientific
inputs rather than hidden code constants. A run must record their source, source
version, path, and SHA-256 digest. Exact mappings may consolidate candidates;
broader, narrower, and related mappings may support only partial compatibility.
Missing mappings remain an explicit limitation and must not be interpreted as
biological conflict.

`scripts/build_phase2_mapping_bundle.py` snapshots the exact InterPro release notes,
Pfam name table, queried InterPro records, reviewed UniProt records, observed candidate
table, and fixture manifest. Its output includes a source manifest and SHA-256 inventory
so the complete small mapping bundle can be moved outside Git to SSD/HPC storage.

## Storage estimate
Practical planning range for this project: **250–600 GB** active use.

The on-demand AlphaFold cache reduces predicted-structure storage, but local eggNOG
and Foldseek databases and indexes still dominate capacity planning.

Recommended device:
- 2 TB external SSD for normal multi-organism research
- 4 TB SSD for larger repeated experiments
- HPC/shared storage for metagenomic/proteome-scale expansion

Reserve substantial free space for Foldseek/MMseqs2 temporary work and index construction.

### Small-volume demo policy

A small-volume device is not a substitute for the research storage target. The current
production profile is `config/4tb-hdd.yaml`; keep database labels and versions
`UNVERIFIED` until their manifests have been populated from the actual data. The
pipeline rejects those placeholders.

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
