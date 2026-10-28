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

## Completed development review

The project owner completed all judgment fields for the 20-report
`phase5-ollama-biological-sections-full-v1` run generated with `gemma3:4b`. The reviewed
TSV SHA-256 is
`190b55b7e087f2b69bd559764f5265964707126ab0e7c98181195b1de5124fa5`.

| Measure | Result |
|---|---:|
| Overall decision | 16 accept, 2 revise, 2 reject |
| Function assessment | 11 correct, 5 plausible, 2 unsure, 2 incorrect |
| Sequence section | 16 correct, 2 partial, 2 incorrect |
| Structure section | 11 correct, 1 partial, 2 incorrect, 6 not available |
| Literature grounding | 13 correct, 5 partial, 2 incorrect |
| Unsupported claims | 20 none |
| Usefulness | 14 useful, 3 partly useful, 3 not useful |

This closes the 20-report development-review task. It does not validate another model,
replace a blinded baseline comparison, repair the failing Phase 4 scientific exit, or
establish biological correctness on an unseen cohort.
