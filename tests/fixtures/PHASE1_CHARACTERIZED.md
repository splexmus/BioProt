# Phase 1 characterized integration fixture

`phase1_characterized.fasta` contains five reviewed, protein-level-evidence
UniProtKB/Swiss-Prot entries from release 2026_03. The records cover human, yeast,
bacterial, and viral proteins and use the exact canonical sequences in the installed
`uniprot_sprot.fasta.gz` snapshot.

`phase1_characterized_manifest.tsv` records source-derived names, taxonomy, EC,
representative function-relevant GO terms, InterPro/Pfam identifiers, sequence lengths,
and sequence checksums. The GO column is deliberately representative rather than a
complete export. This is a small external-tool integration set, not a statistically
valid benchmark and not evidence that every retrieved annotation is correct.
