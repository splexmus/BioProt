# BioProt web demo

`demo/streamlit_app.py` is a browser demo that anyone can open from a link. It needs no
biological databases, so it runs on a laptop or on free hosting.

| Page | What it shows | Data |
|---|---|---|
| Overview | What BioProt does, the pipeline, the headline result | `benchmark/` |
| Try the pipeline | Runs the real `analyze` code on pasted FASTA | Synthetic fixture backend |
| Explore real proteins | Ranked EC/GO predictions vs curated labels, with sequence and structure evidence, for 47 real proteins | `benchmark/phase3-external-panel-*` |
| Scientific status | Confidence intervals for sequence vs structure vs dual, component scorecard | `benchmark/`, `docs/SCIENTIFIC_STATUS_REPORT.md` |
| About | Data sources, licences, how to run real analyses | — |

**Scientific boundary.** *Try the pipeline* uses synthetic search results. Only the five
example IDs (`Q_CONSENSUS`, `Q_SEQ_ONLY`, `Q_STRUCT_ONLY`, `Q_CONFLICT`, `Q_EMPTY`)
produce hits, and any other protein returns *insufficient evidence*. Real predictions
come only from *Explore real proteins*, which reads results computed on the full Linux
platform. The app says this on every relevant page; keep it that way.

## Run it locally

Windows, Linux, or macOS, from the repository root:

```bash
pixi run demo
```

The first run creates a separate `demo` pixi environment with Streamlit; the default
environment is unchanged. Open <http://localhost:8501>.

## Publish a free public link (Streamlit Community Cloud)

1. Push the branch that contains `demo/` to GitHub.
2. Sign in at <https://share.streamlit.io> with your GitHub account and choose
   **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `splexmus/BioProt`
   - **Branch:** the branch with the demo (for example `feat/windows-support`, or
     `main` after merging)
   - **Main file path:** `demo/streamlit_app.py`
   - **App URL:** pick a name, for example `bioprot`
4. Open **Advanced settings** and choose **Python 3.11** or newer. BioProt needs 3.11+.
5. Click **Deploy**. The first build takes a few minutes. You get a link like
   `https://bioprot.streamlit.app`, and every push to that branch redeploys it.

The build installs `demo/requirements.txt`. It doesn't use pixi and doesn't install the
heavy bioinformatics tools. The app imports BioProt straight from `src/`.

**Private repository:** Community Cloud can deploy from a private repo once you grant
access, but visitors then need to be invited. For an open link, make the repository
public or use Hugging Face Spaces.

**Sleeping apps:** free Community Cloud apps go to sleep after a period without visitors.
The next visitor sees a "wake up" button and waits about 30 seconds.

## Alternative: Hugging Face Spaces

1. Create a new Space at <https://huggingface.co/new-space> and pick the
   **Streamlit** template (Docker-based) with free CPU hardware.
2. Copy `demo/`, `src/`, `config/config.yaml`, `tests/fixtures/`,
   `benchmark/phase3-external-panel-v1/` and `benchmark/phase3-external-panel-run-v1/`
   into the Space repository, keeping the same folder layout.
3. Install `demo/requirements.txt` and start `streamlit run demo/streamlit_app.py
   --server.port 8501` in the Space's Dockerfile.

This keeps the main repository private while the demo is public.

## Updating the demo

- Results for *Explore real proteins* come from committed `benchmark/` files. To show a
  newer run, point `DATASET` and `RUN` at the top of `demo/streamlit_app.py` at the new
  folders.
- The scorecard on *Scientific status* is copied from
  `docs/SCIENTIFIC_STATUS_REPORT.md`. Update `SCORECARD` when that report changes.
- After changing the app, run `pixi run demo` and click through every page before pushing.
