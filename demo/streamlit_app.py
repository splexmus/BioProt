"""BioProt web demo.

Runs with no biological databases: live runs use the synthetic fixture backend, and the
"Real proteins" page reads the preserved Phase 3 external-panel results in benchmark/.

Local:  pixi run demo
Cloud:  Streamlit Community Cloud, main file demo/streamlit_app.py (see docs/DEMO.md)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
# Hosted platforms install demo/requirements.txt, not the package itself.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dualrag.analysis import AnalysisError, run_analysis  # noqa: E402
from dualrag.config import load_config  # noqa: E402

DATASET = ROOT / "benchmark" / "phase3-external-panel-v1"
RUN = ROOT / "benchmark" / "phase3-external-panel-run-v1"
FIXTURE_FASTA = ROOT / "tests" / "fixtures" / "queries.fasta"
FIXTURE_CONFIG = ROOT / "config" / "config.yaml"
REPO_URL = "https://github.com/splexmus/BioProt"

BASELINES = {
    "B2_SEQUENCE_ONLY": "Sequence only",
    "B3_STRUCTURE_ONLY": "Structure only",
    "B4_DUAL_DETERMINISTIC": "Dual (sequence + structure)",
}
# Reference categorical palette, first three slots (validated all-pairs, both modes).
PALETTE = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a"],
    "dark": ["#3987e5", "#d95926", "#199e70"],
}
STATE_BADGES = {
    "CONSENSUS": ":green-badge[CONSENSUS]",
    "PARTIAL_CONSENSUS": ":green-badge[PARTIAL CONSENSUS]",
    "SEQUENCE_ONLY": ":blue-badge[SEQUENCE ONLY]",
    "STRUCTURE_ONLY": ":violet-badge[STRUCTURE ONLY]",
    "CONFLICT": ":orange-badge[CONFLICT]",
    "INSUFFICIENT_EVIDENCE": ":gray-badge[INSUFFICIENT EVIDENCE]",
}
SCENARIOS = {
    "Q_CONSENSUS": "Sequence and structure agree on the same function.",
    "Q_SEQ_ONLY": "Only sequence homology finds a function.",
    "Q_STRUCT_ONLY": "Only structural similarity finds a function.",
    "Q_CONFLICT": "The two channels point to different functions; both are kept.",
    "Q_EMPTY": "Neither channel finds informative evidence, so the pipeline abstains.",
}
# From docs/SCIENTIFIC_STATUS_REPORT.md (assessment date 2026-11-07).
SCORECARD = [
    ("Sequence retrieval", "Engineering pass", "Reproducible, useful candidates; strongest"),
    ("Structure retrieval", "Engineering pass", "Independent evidence; AlphaFold = predicted"),
    ("Dual ranking", "No measurable benefit", "Validation cohort: +0.0046, CI −0.014 to 0.023"),
    ("Abstention", "Useful", "80.4% coverage; 6.3% of abstained calls were correct"),
    ("Confidence calibration", "Fail", "Brier 0.257, log loss 0.708, ECE 0.138"),
    ("Literature retrieval", "Fail", "Recall@10 0.46, citation recall 0.27"),
    ("LLM draft reports", "Development pass", "Grounded, citation-checked; expert review pending"),
]
METRIC_LABELS = {
    "function_recall_at_1": "Recall@1",
    "function_recall_at_5": "Recall@5",
    "function_recall_at_10": "Recall@10",
    "mrr": "MRR",
}

st.set_page_config(page_title="BioProt demo", page_icon="🧬", layout="wide")


# --------------------------------------------------------------------------- data


def _tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


@st.cache_data
def load_panel() -> dict[str, pd.DataFrame]:
    queries = _tsv(DATASET / "queries.tsv")
    queries = queries[queries["inclusion_status"] == "INCLUDED_EXTERNAL_CASE"]
    fasta_to_accession = dict(zip(queries["fasta_id"], queries["accession"], strict=True))
    seq = _tsv(RUN / "raw" / "sequence_evidence.tsv")
    struct = _tsv(RUN / "raw" / "structure_evidence.tsv")
    for frame in (seq, struct):
        frame["accession"] = frame["query_id"].map(fasta_to_accession)
    gold = _tsv(DATASET / "gold_labels.tsv")
    gold["key"] = gold.apply(
        lambda row: f"EC:{row['identifier']}" if row["namespace"] == "EC" else row["identifier"],
        axis=1,
    )
    predictions = _tsv(RUN / "predictions.tsv")
    predictions["rank"] = predictions["rank"].astype(int)
    predictions["score"] = predictions["score"].astype(float)
    per_query = _tsv(RUN / "evaluation" / "per_query_metrics.tsv")
    for column in ("function_recall_at_1", "function_recall_at_10", "mrr"):
        per_query[column] = per_query[column].astype(float)
    return {
        "queries": queries,
        "gold": gold,
        "predictions": predictions,
        "per_query": per_query,
        "difficulty": _tsv(DATASET / "difficulty_strata.tsv"),
        "sequence": seq,
        "structure": struct,
        "exclusions": _tsv(RUN / "raw" / "structure_exclusions.tsv"),
        "aggregate": _tsv(RUN / "evaluation" / "aggregate_metrics.tsv"),
    }


@st.cache_data
def load_primary_comparison() -> dict:
    return json.loads((RUN / "evaluation" / "primary_comparison.json").read_text("utf-8"))


def theme_palette() -> list[str]:
    try:
        mode = st.context.theme.type or "light"
    except AttributeError:
        mode = "light"
    return PALETTE["dark" if mode == "dark" else "light"]


COLUMN_LABELS = {
    "target_id": "Hit",
    "target_structure_id": "PDB chain",
    "protein_name": "Protein name",
    "sequence_identity": "Identity",
    "alignment_coverage": "Coverage",
    "query_coverage": "Query coverage",
    "evalue": "E-value",
    "tm_score": "TM-score",
    "ec_numbers": "EC",
    "structure_source": "Source",
    "rank": "Rank",
    "identifier": "Function",
    "modalities": "Supported by",
    "candidate_id": "Candidate",
    "candidate_labels": "Label",
    "cross_modal_status": "State",
    "rerank_score": "Score",
    "namespace": "Type",
    "evidence_code": "Evidence",
    "supporting_reference": "References",
    "protein_name_short": "Protein",
    "taxonomy_superkingdom": "Domain of life",
}


def show_table(frame: pd.DataFrame, **kwargs) -> None:
    """Render a table with readable headers, no index, and full width."""
    kwargs.setdefault("hide_index", True)
    kwargs.setdefault("width", "stretch")
    st.dataframe(frame.rename(columns=COLUMN_LABELS), **kwargs)


# --------------------------------------------------------------------------- pages


def overview_page() -> None:
    st.title("BioProt")
    st.markdown(
        "**Dual-retrieval research platform for protein function.** BioProt looks for a "
        "protein's function through two independent channels, **sequence similarity** "
        "and **3-D structure similarity**, and keeps the two sources of evidence separate "
        "instead of averaging away their disagreements."
    )
    st.graphviz_chart(
        """
        digraph {
          rankdir=LR; bgcolor="transparent";
          node [shape=box, style="rounded", fontname="sans-serif", fontsize=11];
          edge [color="#8a8a8a"];
          input [label="FASTA or\\nUniProt ID"];
          seq [label="Sequence search\\neggNOG-mapper / MMseqs2"];
          af [label="AlphaFold model"];
          fs [label="Structure search\\nFoldseek vs PDB"];
          fuse [label="Function candidates\\nCONSENSUS · CONFLICT ·\\nsingle-channel"];
          lit [label="Literature evidence\\nPubMed / PMC (optional)"];
          rep [label="Grounded draft report\\nlocal LLM (optional)"];
          input -> seq -> fuse; input -> af -> fs -> fuse; fuse -> lit -> rep;
        }
        """
    )
    panel = load_panel()
    comparison = load_primary_comparison()
    aggregate = panel["aggregate"].set_index(["baseline", "metric"])["estimate"].astype(float)
    cols = st.columns(4)
    cols[0].metric("Real proteins in the external panel", len(panel["queries"]))
    cols[1].metric(
        "Recall@10, sequence only",
        f"{aggregate[('B2_SEQUENCE_ONLY', 'function_recall_at_10')]:.3f}",
    )
    cols[2].metric(
        "Recall@10, dual",
        f"{aggregate[('B4_DUAL_DETERMINISTIC', 'function_recall_at_10')]:.3f}",
        delta=f"{comparison['estimate']:+.4f}",
        delta_color="off",
    )
    cols[3].metric("Dual vs sequence", "No gain", help=comparison["conclusion"])
    st.info(
        "BioProt is a working **research instrument**, not a validated predictor. Its "
        "rankings are hypotheses for expert review; scores are not probabilities.",
        icon="ℹ️",
    )
    st.subheader("What you can do in this demo")
    left, middle, right = st.columns(3)
    with left, st.container(border=True):
        st.markdown("**Try the pipeline**")
        st.caption("Run the real pipeline code end to end on five built-in test cases.")
        st.page_link(PAGES["try"], label="Open", icon="▶️")
    with middle, st.container(border=True):
        st.markdown("**Explore real proteins**")
        st.caption("Ranked predictions and evidence for 47 real proteins vs curated labels.")
        st.page_link(PAGES["real"], label="Open", icon="🔬")
    with right, st.container(border=True):
        st.markdown("**Scientific status**")
        st.caption("What has and hasn't been validated, with confidence intervals.")
        st.page_link(PAGES["status"], label="Open", icon="📊")


def try_page() -> None:
    st.title("Try the pipeline")
    st.markdown(
        "This runs BioProt's real analysis code: input validation, both retrieval "
        "channels, normalization, fusion, conflict detection, and the summary report."
    )
    st.warning(
        "**Synthetic test mode.** The hosted demo has no sequence or structure databases "
        "(about 600 GB), so it uses built-in **synthetic** search results. They show how the "
        "pipeline behaves, but they are **not biological predictions**. Proteins other than "
        "the five examples will come back as *insufficient evidence*. For real proteins, see "
        "**Explore real proteins**.",
        icon="⚠️",
    )
    fixture_text = FIXTURE_FASTA.read_text(encoding="utf-8")
    with st.expander("The five example cases", expanded=True):
        for query_id, description in SCENARIOS.items():
            st.markdown(f"- `{query_id}`: {description}")
    fasta_text = st.text_area("FASTA input", value=fixture_text, height=230)
    if st.button("Run analysis", type="primary", icon="▶️"):
        previous = st.session_state.pop("demo_workdir", None)
        if previous:
            shutil.rmtree(previous, ignore_errors=True)
        workdir = Path(tempfile.mkdtemp(prefix="bioprot-demo-"))
        fasta_path = workdir / "input.fasta"
        fasta_path.write_text(fasta_text.strip() + "\n", encoding="utf-8")
        with st.status("Running BioProt…", expanded=False) as status:
            st.write("Validating FASTA input")
            st.write("Sequence and structure retrieval (synthetic backend)")
            st.write("Normalization, fusion, and conflict detection")
            try:
                run_analysis(
                    config=load_config(FIXTURE_CONFIG),
                    output_dir=workdir / "analysis",
                    fasta_path=fasta_path,
                )
            except AnalysisError as error:
                status.update(label="Analysis failed", state="error")
                st.error(f"Could not analyze this input: {error}")
                shutil.rmtree(workdir, ignore_errors=True)
                return
            status.update(label="Analysis complete", state="complete")
        st.session_state["demo_workdir"] = str(workdir)
    workdir_text = st.session_state.get("demo_workdir")
    if workdir_text and (Path(workdir_text) / "analysis" / "status.json").is_file():
        render_analysis(Path(workdir_text) / "analysis")


def render_analysis(output: Path) -> None:
    biological = output / "biological"
    summary = _tsv(biological / "fusion_summary.tsv")
    candidates = _tsv(biological / "function_candidates.tsv")
    sequence = _tsv(biological / "sequence_results.tsv")
    structure = _tsv(biological / "structure_results.tsv")
    status = json.loads((output / "status.json").read_text("utf-8"))

    st.subheader("Results")
    cols = st.columns(3)
    cols[0].metric("Proteins analyzed", status["query_count"])
    cols[1].metric("Confidence", "Not calibrated")
    cols[2].metric("Use", "Hypotheses only")

    for row in summary.to_dict("records"):
        query_id = row["query_id"]
        with st.container(border=True):
            badge = STATE_BADGES.get(row["cross_modal_status"], "")
            st.markdown(f"#### `{query_id}` &nbsp; {badge}")
            st.caption(row["classification_reason"].capitalize())
            if row["top_candidate_id"]:
                st.markdown(
                    f"**Top candidate:** {row['top_candidate_labels'] or row['top_candidate_id']} "
                    f"(`{row['top_candidate_id']}`), ranking score "
                    f"{float(row['top_candidate_score']):.3f} *(not a probability)*"
                )
            else:
                st.markdown("**No function proposed.** BioProt abstains rather than guess.")
            left, right = st.columns(2)
            with left:
                st.markdown("**Sequence evidence**")
                hits = sequence[sequence["query_id"] == query_id]
                if hits.empty:
                    st.caption("No sequence hits.")
                else:
                    show_table(
                        hits[["target_id", "protein_name", "sequence_identity",
                              "alignment_coverage", "evalue"]],
                    )  # fmt: skip
            with right:
                st.markdown("**Structure evidence**")
                hits = structure[structure["query_id"] == query_id]
                if hits.empty:
                    st.caption("No structure hits.")
                else:
                    show_table(
                        hits[["target_structure_id", "protein_name", "tm_score",
                              "query_coverage", "structure_source"]],
                    )  # fmt: skip
            ranked = candidates[candidates["query_id"] == query_id]
            if not ranked.empty:
                with st.expander("All function candidates"):
                    show_table(
                        ranked[["rank", "candidate_id", "candidate_labels", "modalities",
                                "cross_modal_status", "rerank_score"]],
                    )  # fmt: skip

    with st.expander("Full text summary (summary.md)"):
        st.markdown((output / "summary.md").read_text(encoding="utf-8"))
    archive = shutil.make_archive(str(output.parent / "bioprot-demo-results"), "zip", output)
    st.download_button(
        "Download all output files (.zip)",
        data=Path(archive).read_bytes(),
        file_name="bioprot-demo-results.zip",
        mime="application/zip",
        icon="⬇️",
        on_click="ignore",
    )


def real_page() -> None:
    st.title("Explore real proteins")
    st.markdown(
        "Results from BioProt's **independent external panel**: 47 reviewed UniProt "
        "proteins, from archaea, bacteria and eukaryotes, that were screened to exclude "
        "data leakage before the run. Each protein has curated "
        "function labels (EC numbers and GO molecular-function terms), so you can see "
        "where each retrieval channel gets it right."
    )
    panel = load_panel()
    queries = panel["queries"].set_index("accession")
    per_query = panel["per_query"]
    recall = per_query.pivot(
        index="query_accession", columns="baseline", values="function_recall_at_10"
    )

    options = list(queries.index)
    accession = st.selectbox(
        "Protein",
        options,
        format_func=lambda acc: (
            f"{acc} · {queries.at[acc, 'protein_name']} "
            f"({queries.at[acc, 'organism'].split(' (')[0]})"
        ),
    )
    query = queries.loc[accession]
    difficulty = panel["difficulty"].set_index("accession").loc[accession]

    st.subheader(query["protein_name"])
    st.caption(
        f"{query['organism']} · {query['taxonomy_superkingdom']} · "
        f"{query['sequence_length']} residues"
    )
    links = st.columns(3)
    links[0].link_button("UniProt entry", f"https://www.uniprot.org/uniprotkb/{accession}/entry")
    links[1].link_button("AlphaFold model", f"https://alphafold.ebi.ac.uk/entry/{accession}")
    links[2].link_button("BioProt on GitHub", REPO_URL)

    stratum = difficulty["difficulty_stratum"]
    identity = difficulty["sequence_identity"]
    if stratum == "NO_ALLOWED_HIT":
        st.markdown("**Difficulty:** no allowed close relative in the reference set, a hard case.")
    else:
        st.markdown(
            f"**Difficulty:** closest allowed relative shares "
            f"**{float(identity):.0%}** sequence identity (`{stratum}`)."
        )

    gold = panel["gold"][panel["gold"]["accession"] == accession]
    primary = set(gold.loc[gold["admissible_for_primary"] == "true", "key"])
    annotated = set(gold["key"])
    st.markdown("**Curated labels used for scoring**")
    scored = gold[gold["admissible_for_primary"] == "true"]
    show_table(
        scored[["namespace", "identifier", "evidence_code", "supporting_reference"]],
    )

    st.markdown("**Top 10 predictions per channel**  ·  ✅ matches a curated label")
    namespace = st.segmented_control(
        "Function type",
        ["EC", "GO_MF"],
        default="EC",
        format_func={"EC": "Enzyme (EC number)", "GO_MF": "GO molecular function"}.get,
    )
    predictions = panel["predictions"]
    predictions = predictions[
        (predictions["query_accession"] == accession)
        & (predictions["ablation"] == "ALL_MAPPINGS")
        & (predictions["namespace"] == (namespace or "EC"))
    ]
    columns = st.columns(3)
    for column, (baseline, label) in zip(columns, BASELINES.items(), strict=True):
        with column:
            value = recall.at[accession, baseline] if accession in recall.index else float("nan")
            st.markdown(f"**{label}**")
            st.caption(f"Recall@10 for this protein (EC and GO): {value:.2f}")
            top = predictions[predictions["baseline"] == baseline].nsmallest(10, "rank")
            if top.empty:
                st.caption("No prediction of this type.")
                continue
            top = top.assign(
                match=top["identifier"].map(
                    lambda key: "✅" if key in primary else ("◦" if key in annotated else "")
                )
            )
            show_table(
                top[["rank", "match", "identifier", "modalities"]],
                column_config={"match": st.column_config.TextColumn("", width="small")},
            )
    st.caption("◦ appears in UniProt with lower-tier evidence, so it isn't used for scoring.")

    seq_tab, struct_tab = st.tabs(["Sequence evidence", "Structure evidence"])
    with seq_tab:
        hits = panel["sequence"][panel["sequence"]["accession"] == accession]
        st.caption(f"{len(hits)} MMseqs2 hits against reviewed UniProt (leakage-filtered).")
        show_table(
            hits[["target_id", "protein_name", "sequence_identity", "alignment_coverage",
                  "evalue", "ec_numbers"]],
        )  # fmt: skip
    with struct_tab:
        hits = panel["structure"][panel["structure"]["accession"] == accession]
        excluded = (panel["exclusions"]["query_accession"] == accession).sum()
        st.caption(
            f"{len(hits)} Foldseek hits from the AlphaFold model against the PDB; "
            f"{excluded} hits were removed for leakage (the same or a too-similar protein)."
        )
        show_table(
            hits[["target_structure_id", "protein_name", "tm_score", "query_coverage",
                  "sequence_identity", "ec_numbers"]],
        )  # fmt: skip

    st.divider()
    st.subheader("All 47 proteins")
    table = queries[["protein_name", "taxonomy_superkingdom"]].join(recall, how="left")
    table = table.rename(columns=BASELINES)
    table["Dual minus sequence"] = (
        table[BASELINES["B4_DUAL_DETERMINISTIC"]] - table[BASELINES["B2_SEQUENCE_ONLY"]]
    )
    st.caption("Recall@10 per protein. Sort a column to see where structure helped or hurt.")
    show_table(
        table.reset_index(names="accession"),
        column_config={
            name: st.column_config.ProgressColumn(name, min_value=0.0, max_value=1.0, format="%.2f")
            for name in BASELINES.values()
        }
        | {"Dual minus sequence": st.column_config.NumberColumn(format="%+.2f")},
    )


def status_page() -> None:
    st.title("Scientific status")
    st.markdown(
        "BioProt was evaluated against pre-registered (frozen) success criteria. Here is "
        "where it stands as of the **2026-11-07** status report."
    )
    panel = load_panel()
    aggregate = panel["aggregate"]
    aggregate = aggregate[aggregate["metric"].isin(METRIC_LABELS)].copy()
    for column in ("estimate", "ci_lower", "ci_upper"):
        aggregate[column] = aggregate[column].astype(float)
    aggregate["Channel"] = aggregate["baseline"].map(BASELINES)
    aggregate["Metric"] = aggregate["metric"].map(METRIC_LABELS)

    st.subheader("External panel: does adding structure help?")
    st.caption("Point estimate with 95% bootstrap confidence interval, 47 proteins.")
    colors = alt.Scale(domain=list(BASELINES.values()), range=theme_palette())
    base = alt.Chart(aggregate).encode(
        y=alt.Y("Metric:N", sort=list(METRIC_LABELS.values()), title=None),
        yOffset=alt.YOffset("Channel:N", sort=list(BASELINES.values())),
        color=alt.Color("Channel:N", scale=colors, legend=alt.Legend(orient="top", title=None)),
        tooltip=[
            "Channel:N",
            "Metric:N",
            alt.Tooltip("estimate:Q", format=".3f", title="Estimate"),
            alt.Tooltip("ci_lower:Q", format=".3f", title="95% CI low"),
            alt.Tooltip("ci_upper:Q", format=".3f", title="95% CI high"),
        ],
    )
    interval = base.mark_rule(strokeWidth=2).encode(
        x=alt.X("ci_lower:Q", scale=alt.Scale(domain=[0, 1]), title="Score (higher is better)"),
        x2="ci_upper:Q",
    )
    point = base.mark_circle(size=90, opacity=1).encode(x="estimate:Q")
    st.altair_chart(
        (interval + point).properties(height=320).configure_axis(grid=False),
        width="stretch",
    )
    with st.expander("Table view"):
        show_table(
            aggregate[["Metric", "Channel", "estimate", "ci_lower", "ci_upper"]],
            column_config={c: st.column_config.NumberColumn(format="%.3f")
                           for c in ("estimate", "ci_lower", "ci_upper")},
        )  # fmt: skip
    comparison = load_primary_comparison()
    st.markdown(
        f"Primary test, dual minus sequence on Recall@10: **{comparison['estimate']:+.4f}** "
        f"(95% CI {comparison['ci_lower']:+.3f} to {comparison['ci_upper']:+.3f}) → "
        f"`{comparison['conclusion']}`. Sequence search is the strongest single channel; "
        "structure adds coverage and catches some cases sequence misses, but gives no "
        "measurable average gain."
    )

    st.subheader("Component scorecard")
    show_table(
        pd.DataFrame(SCORECARD, columns=["Component", "Decision", "Evidence"]),
    )
    st.markdown(
        "**Appropriate use:** exploratory research, candidate generation, and reviewing "
        "where sequence and structure agree or disagree. **Not** experimental confirmation, "
        "a production annotation service, or a source of calibrated probabilities."
    )


def about_page() -> None:
    st.title("About this demo")
    st.markdown(
        f"""
**Source code:** [{REPO_URL}]({REPO_URL})

**How this demo works.** The *Try the pipeline* page runs the unmodified BioProt
pipeline with its synthetic fixture backend, because the real databases (about 600 GB)
can't be hosted for free. The *Real proteins* page reads results that were computed on
the full Linux platform and are committed under `benchmark/`.

**Run real analyses yourself** on Linux or Windows WSL2 with the databases installed:

```bash
pixi install --locked
pixi run python -m dualrag analyze --uniprot P69905 \\
  --config config/4tb-hdd.yaml --output results/P69905
```

**Data sources and credits.** Protein records and curated labels: UniProtKB/Swiss-Prot
(CC BY 4.0). Structure models: AlphaFold Protein Structure Database, EMBL-EBI and Google
DeepMind (CC BY 4.0). Experimental structures: RCSB Protein Data Bank (CC0), with
SIFTS mappings from PDBe. Function ontologies: Gene Ontology (CC BY 4.0) and ENZYME/EC
numbers. Tools: MMseqs2, Foldseek, eggNOG-mapper, InterPro/Pfam.

**Scientific boundary.** All outputs are putative hypotheses. Ranking scores order
candidates; they are not probabilities and do not confirm function experimentally.
"""
    )


PAGES = {
    "overview": st.Page(overview_page, title="Overview", icon="🧬", default=True),
    "try": st.Page(try_page, title="Try the pipeline", icon="▶️", url_path="try"),
    "real": st.Page(real_page, title="Explore real proteins", icon="🔬", url_path="proteins"),
    "status": st.Page(status_page, title="Scientific status", icon="📊", url_path="status"),
    "about": st.Page(about_page, title="About", icon="ℹ️", url_path="about"),
}

st.navigation(list(PAGES.values()), position="top").run()
