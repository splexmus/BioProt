# ENVIRONMENT.md

## Recommended platform
- Linux workstation, WSL2, or HPC Linux
- Conda/Mamba
- Python 3.11
- conda-forge + bioconda with strict channel priority

## Core Conda environment

```bash
conda create -n bioinfo python=3.11 -y
conda activate bioinfo
conda config --add channels conda-forge
conda config --add channels bioconda
conda config --set channel_priority strict
```

Recommended bioinformatics/scientific packages:

```bash
conda install -y \
  mmseqs2 \
  foldseek \
  hmmer \
  blast \
  diamond \
  eggnog-mapper \
  biopython \
  gemmi \
  numpy \
  pandas \
  scipy \
  scikit-learn \
  pyarrow \
  matplotlib \
  statsmodels \
  networkx \
  faiss-cpu \
  tqdm \
  requests \
  pyyaml
```

Python/RAG packages added later:

```bash
pip install \
  torch \
  transformers \
  sentence-transformers \
  accelerate \
  sentencepiece \
  beautifulsoup4 \
  lxml \
  pymupdf \
  pypdf \
  pydantic \
  python-dotenv \
  typer \
  rich \
  pytest \
  pytest-cov \
  ruff \
  black
```

Optional integrations:

```bash
pip install openai neo4j mlflow
```

Do not add LangChain/LlamaIndex to the MVP unless they solve a demonstrated problem. Plain Python orchestration is preferred initially.

## Suggested `environment.yml`

```yaml
name: dualrag
channels:
  - conda-forge
  - bioconda
  - defaults
dependencies:
  - python=3.11
  - mmseqs2
  - foldseek
  - hmmer
  - blast
  - diamond
  - eggnog-mapper
  - biopython
  - gemmi
  - numpy
  - pandas
  - scipy
  - scikit-learn
  - pyarrow
  - matplotlib
  - statsmodels
  - networkx
  - faiss-cpu
  - tqdm
  - requests
  - pyyaml
  - pip
  - pip:
      - pydantic
      - python-dotenv
      - typer
      - rich
      - pytest
      - pytest-cov
      - ruff
      - black
```

Add large ML packages only when the RAG phase begins to keep the early environment lighter and easier to solve.

## Storage plan
Recommended local research configuration:

```text
Internal SSD
├── Conda installation/environments
├── repository source
└── small active fixtures

External 2 TB+ SSD or HPC storage
├── databases/
│   ├── eggnog/              # local annotation/search database
│   ├── foldseek/            # local structure-search target database
│   └── optional local sequence databases/
├── alphafold_cache/         # only REST-fetched query models
├── literature_cache/
├── indexes/
├── tmp/
├── results/
└── experiments/
```

Approximate planning budget:
- Conda + Python tools: 10–25 GB
- eggNOG and indexes/extras: tens to >100 GB depending on selected components
- Foldseek/PDB database: tens of GB depending on representation/version
- AlphaFold on-demand query-model cache: normally small; bound it with a retention policy
- literature cache/vector index: 10s of GB for moderate use
- temporary/intermediate results: reserve 50–300 GB

Project planning target: **250–600 GB** active footprint; **2 TB SSD recommended**.

## Environment variables

```bash
export DUALRAG_DATA_ROOT=/external_ssd/dualrag
export EGGNOG_DATA_DIR=$DUALRAG_DATA_ROOT/databases/eggnog
export DUALRAG_FOLDSEEK_DB=$DUALRAG_DATA_ROOT/databases/foldseek/pdb
export DUALRAG_ALPHAFOLD_API_URL=https://alphafold.ebi.ac.uk/api
export DUALRAG_TMP=$DUALRAG_DATA_ROOT/tmp
export DUALRAG_RESULTS=$DUALRAG_DATA_ROOT/results
```

## Version capture
Every experiment must record:

```bash
python --version
mmseqs version
foldseek version
emapper.py --version || true
hmmsearch -h | head
blastp -version
```

Also record database versions/dates separately because software version alone is insufficient for reproducibility.
