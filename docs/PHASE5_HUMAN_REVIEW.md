# Phase 5 human report review

The review table is generated from the complete 20-report
`phase5-ollama-biological-sections-full-v1` run. Automated columns are locked provenance
and context summaries. Reviewers should fill only the columns beginning with
`function_assessment` plus `reviewer`, `review_date`, and `notes`.

Use these controlled values:

| Column | Allowed values |
|---|---|
| `function_assessment` | `CORRECT`, `PLAUSIBLE`, `INCORRECT`, `UNSURE` |
| sequence/structure section | `CORRECT`, `PARTIAL`, `INCORRECT`, `NA` |
| `cross_modal_handling` | `CORRECT`, `PARTIAL`, `INCORRECT` |
| literature/citation grounding | `CORRECT`, `PARTIAL`, `INCORRECT`, `NA` |
| `unsupported_claims` | `NONE`, `MINOR`, `MAJOR` |
| `report_usefulness` | `USEFUL`, `PARTLY_USEFUL`, `NOT_USEFUL` |
| `overall_decision` | `ACCEPT`, `REVISE`, `REJECT` |

Review sequence and structure claims against their displayed identities, coverage,
TM-scores, annotations, and provenance. A plausible prediction is not automatically
`CORRECT`; use `PLAUSIBLE` or `UNSURE` when the evidence supports a hypothesis but does
not establish exact function. A structure section may be `NA` only when the recorded
structure-hit count is zero.

For literature, check that passages refer to the correct protein or a traceable homolog,
that organism differences are not hidden, and that unassessed passages remain background.
Any invented function, identifier, active site, pathway, experiment, or citation is a
major unsupported claim.

The completed table measures development report quality. It is not blinded expert
comparison unless reviewers are blinded to system variant and baseline identity.
