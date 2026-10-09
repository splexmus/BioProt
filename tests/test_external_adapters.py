from __future__ import annotations

import json
from pathlib import Path

from dualrag.config import AlphaFoldApiConfig, SequenceConfig, StructureConfig
from dualrag.models import ProteinQuery
from dualrag.sequence import eggnog
from dualrag.structure import foldseek
from dualrag.structure.alphafold import acquire_models, resolve_accession


def test_parse_eggnog_annotations(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "run.emapper.annotations"
    path.write_text(
        "## emapper test\n"
        "#query\tseed_ortholog\tevalue\tscore\teggNOG_OGs\tDescription\tGOs\tEC\t"
        "KEGG_ko\tKEGG_Pathway\tKEGG_Module\tKEGG_Reaction\tPFAMs\n"
        "P12345\t9606.ENSP1\t1e-30\t250\tOG1\tDemo enzyme\tGO:1,GO:2\t1.2.3.4\t"
        "ko:K1\tmap0001\t-\tR0001\tPF001;PF002\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(eggnog, "_tool_version", lambda executable: "emapper-test")
    config = SequenceConfig(
        backend="local",
        eggnog_data_dir=tmp_path,
        database_name="eggNOG",
        database_version="5.0.2",
    )
    hits = eggnog.parse_annotations(path, [ProteinQuery("P12345", "MPEPTIDE")], config)
    assert len(hits) == 1
    assert hits[0].target_id == "9606.ENSP1"
    assert hits[0].go_terms == ["GO:1", "GO:2"]
    assert hits[0].kegg_terms == ["R0001", "ko:K1", "map0001"]
    assert hits[0].sequence_identity is None


def test_accession_resolution_is_explicit() -> None:
    assert resolve_accession(ProteinQuery("sp|P69905|HBA_HUMAN", "M")) == (
        "P69905",
        "fasta_uniprot_pipe",
    )
    assert resolve_accession(ProteinQuery("P69905", "M")) == ("P69905", "validated_query_id")
    assert resolve_accession(ProteinQuery("my_protein", "M")) == (None, "unresolved")


class _Response:
    def __init__(self, status_code: int, payload: object = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Session:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata

    def get(self, url: str, timeout: float) -> _Response:
        if "/prediction/" in url:
            return _Response(200, [self.metadata])
        return _Response(200, content=b"data_demo\n")


class _NotFoundSession:
    def get(self, url: str, timeout: float) -> _Response:
        return _Response(404)


def test_alphafold_download_and_cache(tmp_path: Path) -> None:
    query = ProteinQuery("P69905", "MPEPTIDE")
    metadata = {
        "uniprotAccession": "P69905",
        "uniprotSequence": "MPEPTIDE",
        "entryId": "AF-P69905-F1",
        "latestVersion": 4,
        "cifUrl": "https://example.test/model.cif",
    }
    config = AlphaFoldApiConfig(enabled=True, request_interval_seconds=0)
    cache, raw = tmp_path / "cache", tmp_path / "raw"
    models, records = acquire_models([query], cache, raw, config, _Session(metadata))
    assert models["P69905"].read_bytes() == b"data_demo\n"
    assert records[0].status == "DOWNLOADED"
    assert records[0].sequence_compatible is True
    assert json.loads((raw / "P69905.metadata.json").read_text())[0]["entryId"] == "AF-P69905-F1"
    models, records = acquire_models([query], cache, raw, config, _Session(metadata))
    assert models["P69905"].exists()
    assert records[0].status == "CACHED"


def test_alphafold_404_is_model_unavailable(tmp_path: Path) -> None:
    query = ProteinQuery("P69905", "MPEPTIDE")
    config = AlphaFoldApiConfig(enabled=True, request_interval_seconds=0)
    models, records = acquire_models(
        [query], tmp_path / "cache", tmp_path / "raw", config, _NotFoundSession()
    )
    assert models == {}
    assert records[0].status == "NOT_FOUND"
    assert records[0].http_status == 404


def test_parse_foldseek_results_with_metadata(tmp_path: Path, monkeypatch) -> None:
    results = tmp_path / "hits.tsv"
    results.write_text("q000000\t1abc_A\t1e-8\t80\t0.72\t100\t0.8\t0.7\t0.25\n")
    metadata = tmp_path / "metadata.tsv"
    metadata.write_text(
        "target_structure_id\ttarget_uniprot_id\tprotein_name\tinterpro_ids\t"
        "supfam_ids\tstructure_source\texperimental_structure\tsource_accession\n"
        "1abc_A\tP1\tDemo enzyme\tIPR1\tSSF1\tPDB\ttrue\t1abc\n"
    )
    monkeypatch.setattr(foldseek, "_tool_version", lambda executable: "foldseek-test")
    config = StructureConfig(
        backend="hybrid",
        foldseek_db=tmp_path / "db",
        target_metadata=metadata,
        alphafold_cache=tmp_path / "cache",
        alphafold_api=AlphaFoldApiConfig(enabled=True),
        database_name="demo",
        database_version="2026-10-07",
    )
    hits = foldseek.parse_results(results, {"q000000": "P69905"}, config)
    assert hits[0].query_id == "P69905"
    assert hits[0].tm_score == 0.72
    assert hits[0].experimental_structure is True
    assert hits[0].structure_source == "PDB"
