# Phase 4.3 PubMed adapter plan

Implementation status: complete as the versioned `pubmed-eutils-v1` baseline on
2026-10-26. Live HDD acquisition remains pending because the external filesystem was
read-only during validation. See `docs/PHASE4_PIPELINE.md` for commands and the Phase
4.4-4.7 continuation.

Phase 4.3 will implement PubMed as a metadata-and-abstract adapter. It will not treat a
PubMed citation as available full text and will not assign `SUPPORT` merely because an
article was retrieved.

NCBI E-utilities are the official programmatic interface to PubMed. The planned request
pipeline is `ESearch → EFetch`: ESearch resolves a query to PMIDs and EFetch downloads
batched PubMed XML records containing citation metadata and abstracts. See the official
[NCBI E-utilities overview](https://www.ncbi.nlm.nih.gov/books/NBK25497/) and
[API landing page](https://www.ncbi.nlm.nih.gov/home/develop/api/).

## 4.3A Configuration and client boundary

Add a typed `PubMedConfig` containing:

- configurable E-utilities base URL;
- required application `tool` and contact `email`;
- optional API-key environment-variable name, never the key value in snapshots;
- connect/read timeout;
- bounded retries with exponential backoff and jitter;
- request pacing;
- maximum PMIDs retrieved per query variant;
- EFetch batch size;
- raw-response and cache directories.

The client will send requests to `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`, record
the complete non-secret parameters, and comply with NCBI's published scripting policy.
NCBI currently limits clients without an API key to three requests per second and asks
software to supply `tool` and `email`; the adapter will default below that rate. With an
API key it may use the documented higher rate, but conservative batching remains the
default. See [NCBI scripting-call policy](https://www.ncbi.nlm.nih.gov/home/about/policies/).

## 4.3B Deterministic PubMed translation

Translate each Phase 4.2 source-neutral variant without adding biological concepts:

- protein accessions, protein names, candidate labels, and controlled IDs become
  explicit PubMed text clauses;
- organism terms use a fixed, versioned field strategy;
- quoting and reserved-character escaping are deterministic;
- the exact translated string and translation version are stored;
- no spelling expansion, synonym inference, MeSH explosion, or model-generated term is
  introduced in v1.

The adapter will retain PubMed's returned query translation separately so unexpected
search-engine rewriting is auditable.

## 4.3C Search and batching

For every query variant:

1. call ESearch with `db=pubmed`, deterministic result limit, and relevance sort;
2. preserve returned PMIDs, original rank, result count, and PubMed query translation;
3. deduplicate PMIDs across variants while retaining every contributing variant/rank;
4. batch unique PMIDs into EFetch PubMed XML requests;
5. avoid one-request-per-article behavior;
6. stop at the configured candidate-pool limit before downstream reranking.

For large result sets, the adapter will support Entrez History (`WebEnv` and
`query_key`) rather than transmitting large identifier lists. NCBI recommends batching
and History-server workflows to minimize requests.

## 4.3D XML normalization

Parse PubMed XML into `ArticleMetadata` while retaining:

- PMID, PMCID when present, DOI and other article identifiers;
- complete title and structured abstract sections;
- publication year/date and journal;
- publication types and review status;
- author-supplied keywords and MeSH terms as metadata, not automatic evidence;
- retraction, correction, or update relationships;
- source URL, retrieval time, raw-response path, and response checksum.

Missing abstract, year, DOI, or PMCID stays null. A record without PMCID becomes
`ABSTRACT_ONLY` or `METADATA_ONLY`; it is not considered negative evidence.

## 4.3E Deduplication and provenance

Deduplicate by PMID, then PMCID, then normalized DOI. Preserve all query variants that
found the article and its best and original ranks. Raw ESearch JSON and EFetch XML are
immutable run artifacts; normalized JSONL is written separately. Cache keys include the
endpoint, database, translated query or PMID batch, relevant parameters, and adapter
version.

## 4.3F Failures and retries

- Retry timeouts, HTTP 429, and transient 5xx responses with bounded backoff.
- Respect `Retry-After` when supplied.
- Do not retry permanent 4xx request errors except 429.
- Record malformed XML and per-record parse failures without silently dropping them.
- Resume from verified cached responses.
- Redact API keys from logs, manifests, errors, and config snapshots.

## 4.3G Outputs

The PubMed subadapter will write:

```text
raw/pubmed/esearch/<request-hash>.json
raw/pubmed/efetch/<request-hash>.xml
pubmed_searches.jsonl
article_metadata.jsonl
pubmed_acquisition_manifest.json
```

The manifest will record query counts, PMID counts, duplicate collapse, abstract/full-
text availability, HTTP outcomes, retries, cache state, adapter version, commands, and
checksums.

## 4.3H Tests and completion condition

Routine tests will mock the HTTP boundary and cover:

- deterministic parameter translation;
- ESearch pagination and PubMed query translation;
- EFetch batching;
- duplicate PMID/PMCID/DOI handling;
- structured and missing abstracts;
- review and publication-type detection;
- PMCID and DOI extraction;
- timeout, 429, 5xx, malformed XML, and partial-record behavior;
- cache reuse and secret redaction.

One small live smoke request may be run separately and clearly labelled as a network
integration test. The PubMed portion of Phase 4.3 is complete only when real metadata
and abstract records can be retrieved reproducibly and missing full text remains explicit.

PMC Open Access full-text acquisition is a separate source adapter within Phase 4.3. It
uses PMC ESearch access/license filters followed by EFetch and preserves article-specific
license information. The legacy OA Web Service was retired in August 2026; it is not
used. Not every PMC article permits identical reuse. See the official
[PMC developer guidance](https://pmc.ncbi.nlm.nih.gov/tools/developers/).

