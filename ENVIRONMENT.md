# Environment

## Supported platform

- Linux x86-64 workstation, WSL2, or HPC Linux
- Pixi 0.81 or newer
- Python 3.11
- conda-forge + bioconda with strict channel priority

The reproducible environment is defined by `pixi.toml` and the committed `pixi.lock`.
Pixi manages Conda and PyPI packages together; a separate Conda installation or active
Conda environment is not required.

## Install

Install Pixi once if `pixi --version` is unavailable, following the official Pixi
installation instructions. From the repository root, create the locked environment:

```bash
pixi install --locked
```

The environment is stored under the ignored `.pixi/` directory. Enter an interactive
shell only when useful:

```bash
pixi shell --locked
```

Normal project commands do not require activation:

```bash
pixi run test
pixi run lint
pixi run cli
pixi run check-tools
pixi run smoke-fixture
pixi run validate
```

Run an arbitrary command in the environment with `pixi run`, for example:

```bash
pixi run python -m dualrag run \
  --config config/4tb-hdd.yaml \
  --input proteins.fasta \
  --output "$DUALRAG_RESULTS/phase1-smoke"
```

Use `--locked` in CI and published reproductions so a stale manifest/lock pair fails
instead of silently re-solving. Use `pixi update --dry-run` before intentional upgrades,
then rerun the complete validation and commit both manifest and lock changes.

## Dependency policy

The default Pixi environment contains only Phase 1 runtime tools and development checks:

- Python 3.11
- MMseqs2 16.747c6
- Foldseek 9.427df8a
- HMMER 3.4
- BLAST+ 2.16–2.17
- DIAMOND 2.0.x
- eggNOG-mapper 2.1.15
- the editable local `dualrag` package and its declared Python dependencies
- pytest and Ruff

DIAMOND remains on 2.0.x because eggNOG-mapper 2.1.15 requires
`>=2.0.11,<2.1`. Exact transitive package builds and artifact hashes are recorded in
`pixi.lock`; database versions and checksums remain separately recorded in
`config/databases.4tb-hdd.yaml`.

Do not add Torch, Transformers, embedding models, literature tooling, OpenAI clients,
Neo4j, or MLflow to the Phase 1 environment. Add named Pixi features/environments when
those later phases begin so retrieval remains lightweight and independently testable.

The exported `environment.yaml` and `environment-wsl.yaml` files are retained only as
historical Conda snapshots. They are not the supported installation source and should
not be regenerated or used to update the Pixi lockfile.

## Pixi advantages for this project

1. `pixi.lock` pins exact Conda and PyPI artifacts, including hashes, rather than relying
   on a large machine-specific exported environment.
2. The bioinformatics executables and the Python package share one reproducible solve.
3. `pixi run` removes dependence on an activated `bioinfo` environment and makes README,
   CI, WSL, and HPC commands consistent.
4. Named tasks provide one canonical test, lint, CLI, tool-check, and smoke workflow.
5. The manifest lists intentional dependencies only; transitive libraries stay in the
   lockfile. This is much easier to review than the exported Conda YAML files.
6. The installed Phase 1 Pixi environment is about 1.5 GB on this workstation, compared
   with about 8.9 GB for the previous broad Conda environment.
7. Strict conda-forge/bioconda channel resolution is project-local and cannot be changed
   accidentally by a user's global Conda configuration.
8. Future RAG, GPU, and evaluation stacks can be isolated as Pixi features instead of
   making every Phase 1 user install them.
9. `--locked`/`--frozen` modes make accidental dependency drift visible in automation.
10. Pixi does not relocate the biological databases: the existing external-HDD paths,
    manifests, caches, and provenance model continue to work unchanged.

## Pixi disadvantages and risks for this project

1. Pixi is another tool contributors must install, and it is less familiar than Conda in
   some bioinformatics and HPC groups.
2. The current manifest supports `linux-64` only. macOS, ARM, and Windows would require
   separate platform solving and may lack equivalent Bioconda packages.
3. Many institutional HPC systems document Conda/Modules rather than Pixi; users may need
   a user-local Pixi binary or an exported environment supplied by administrators.
4. The first install still downloads large Conda artifacts and uses a shared cache in the
   user's home directory; limited home quotas may require Pixi cache configuration.
5. The project-local `.pixi` environment can consume significant repository-adjacent
   disk space and must remain ignored by Git and backups.
6. Conda/PyPI mixed solving is powerful but adds a second package ecosystem. Native
   libraries should stay on Conda where possible, and unnecessary duplicate packages
   across Conda and PyPI should be avoided.
7. A lockfile guarantees software artifacts, not external biological databases, REST API
   availability, CPU behavior, or filesystem state. Database manifests and run provenance
   remain mandatory.
8. Updating Pixi or re-solving can select a different build of the same nominal tool
   version. Embedded build identifiers are preserved in results and can make historical
   runs intentionally non-equivalent even when biological values are unchanged.
9. Editable installation is convenient for development, but local source changes take
   effect immediately; Git commit identity and dirty-tree state still need recording for
   formal experiments.
10. Existing Conda environments are not converted in place. They remain separate and can
    disagree with Pixi if both workflows continue to be used.

For this repository the advantages outweigh the risks: Pixi is the primary supported
workflow, while the old Conda exports are fallback evidence only.

## Storage plan

```text
Internal SSD
├── Pixi installation, cache, and project environments
├── repository source
└── small active fixtures

External 2 TB+ SSD or HPC storage
├── databases/
│   ├── eggnog/
│   ├── foldseek/
│   └── optional local sequence databases/
├── alphafold_cache/
├── literature_cache/
├── indexes/
├── tmp/
├── results/
└── experiments/
```

Approximate planning budget:

- Pixi Phase 1 environment: approximately 1.5 GB in the validated Linux installation
- eggNOG and indexes/extras: tens to more than 100 GB
- Foldseek/PDB database: tens of GB depending on snapshot
- bounded AlphaFold on-demand cache: normally small
- temporary/intermediate results: reserve 50–300 GB

Project planning target remains **250–600 GB** active data and a **2 TB SSD** for
comfortable research use.

## Environment variables

```bash
export DUALRAG_DATA_ROOT=/external_ssd/dualrag
export EGGNOG_DATA_DIR="$DUALRAG_DATA_ROOT/databases/eggnog"
export DUALRAG_FOLDSEEK_DB="$DUALRAG_DATA_ROOT/databases/foldseek/pdb"
export DUALRAG_ALPHAFOLD_API_URL=https://alphafold.ebi.ac.uk/api
export DUALRAG_TMP="$DUALRAG_DATA_ROOT/tmp"
export DUALRAG_RESULTS="$DUALRAG_DATA_ROOT/results"
```

## Version capture

Every experiment must retain the pipeline's command log and run metadata. For a manual
inventory:

```bash
pixi --version
pixi run python --version
pixi run mmseqs version
pixi run foldseek version
pixi run emapper.py --version || true
pixi run hmmsearch -h | head
pixi run blastp -version
pixi run diamond version
```

Software locking does not replace database version/date/checksum provenance.
