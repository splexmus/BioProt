# REFERENCES.md — Design Basis

These references are the supplied papers that currently shape the project. Keep project claims faithful to what each paper actually demonstrates.

## 1. ProtPen
**Diya Mathai and Stefan Schulze.** “ProtPen Combines Sequence- and Structure-based Approaches to Facilitate Protein Function Predictions on a Proteome-wide Scale.” *Journal of Proteome Research* (2026). DOI: `10.1021/acs.jproteome.6c00074`.

Project-relevant ideas supported by this paper:
- Python-based modular protein annotation workflow.
- Sequence annotation with eggNOG-mapper, using MMseqs2 as the default alignment method in the reported implementation.
- AlphaFold-predicted structure retrieval for query proteins.
- Foldseek structural search, reported against PDB to prioritize experimentally determined structures.
- Enrichment of structural hits with UniProt metadata, including InterPro/SUPFAM information.
- Merging sequence and structure evidence into a unified TSV.
- In its curated Pseudomonas aeruginosa control set, agreement between both tools was treated as the most reliable category.
- The authors explicitly position the system as hypothesis-generating for unknown proteins and note the need for experimental validation.
- Future directions mention more automated/quantitative consensus mechanisms and possible Nextflow/Snakemake adaptation.

How this project extends the idea:
- preserve independent modality scores and calibrate quantitative fusion
- explicit conflict handling
- retrieval evaluation separate from generation
- optional literature RAG and citation verification
- optional graph/path evidence layer

## 2. MicroTraitLLM
**Glen Rogers, James R. Brown, Bahrad A. Sokhansanj, Joshua Mell, and Gail L. Rosen.** “MicroTraitLLM: A RAG-based, Microbe-focused LLM for Researchers.” *BCB '25* (2025). DOI: `10.1145/3765612.3767201`.

Project-relevant ideas supported by this paper:
- user question transformed into NCBI-oriented search behavior
- retrieval of PMC/Open Access article content and metadata
- separate article-level summaries followed by final comprehensive synthesis
- citation-oriented responses and links to external NCBI resources
- LLM and human evaluation
- acknowledgement that LLM-as-a-judge can be biased and that factual/citation evaluation remains important

How this project uses the idea:
- literature retrieval occurs after biological sequence/structure candidate generation
- retain article metadata and evidence provenance
- evaluate citation support rather than assuming citations imply correctness

## 3. GLEAR
**Jingyun Sun, Jiaming Tian, Jie Shi, Yixin Zhang, Wenxi Sheng, and Yang Li.** “GLEAR: A Graph Logic-Enhanced RAG Framework for Legal QA.” *AAMAS 2026*. DOI: `10.65109/ZNVM5881`.

Project-relevant transferable ideas supported by this paper:
- dual-driven retrieval combining two retrieval signals
- explicit structured knowledge representation
- key logical path mining
- dynamic augmentation of the LLM with selected path descriptions
- ablation studies that isolate contributions of graph structure, dual retrieval, and path mining

How this project adapts the idea rather than copying the legal-domain implementation:
- sequence similarity and structure similarity are the two principal biological retrieval channels
- graph nodes may represent proteins, structures, domains, functions, pathways, and publications
- graph/path reasoning is optional and must demonstrate benefit over simpler fusion before adoption

## Reading rule for agents
Do not attribute claims from one paper to another. If a project decision goes beyond these papers, label it as a project design choice or hypothesis rather than as an established result from the cited work.
