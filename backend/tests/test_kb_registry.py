import json

import pytest

import kb_registry

DIAC = "DIAC Rules conclusive_UsingOCR.pdf"


def test_loads_all_files_plus_sop():
    files = kb_registry.approved_files()
    with open(kb_registry._DEFAULT_PATH, encoding="utf-8") as fh:
        names = {r["file_name"] for r in json.load(fh)}  # unique files, not records
    assert files == names | {kb_registry.SOP_FILE}
    assert kb_registry.file_meta(kb_registry.SOP_FILE) == {
        "source_id": "court_bazaar_sop", "title": kb_registry.SOP_FILE}
    assert kb_registry.display_label(kb_registry.SOP_FILE) == "Standard Operating Procedure (SOP)"


def test_unknown_file_returns_none():
    for fn in (kb_registry.file_meta, kb_registry.records_for_file, kb_registry.display_label,
               kb_registry.provision_label, kb_registry.institution, kb_registry.vector_store_attributes):
        assert fn("nope.pdf") is None
    assert kb_registry.instruments("nope.pdf") == ()


def test_diac_keeps_legacy_metadata_and_three_instruments():
    assert kb_registry.file_meta(DIAC) == {"source_id": "diac_rules", "title": DIAC}
    assert kb_registry.display_label(DIAC) == "Delhi International Arbitration Centre (DIAC) Rules"
    assert kb_registry.instruments(DIAC) == (
        ("ARBITRATIONPROCEEDINGS", "Delhi International Arbitration Centre (Arbitration Proceedings) Rules, 2023"),
        ("INTERNALMANAGEMENT", "Delhi International Arbitration Centre (Internal Management) Rules, 2012"),
        ("ADMINISTRATIVECOSTS",
         "Delhi International Arbitration Centre (Administrative Costs & Arbitrators' Fees) Rules, 2018"),
    )
    assert kb_registry.provision_label(DIAC) == "Rule"


def test_file_name_unique_per_page_range():
    seen = set()
    for name in kb_registry.approved_files() - {kb_registry.SOP_FILE}:
        for rec in kb_registry.records_for_file(name):
            key = (rec["file_name"], tuple(rec.get("page_range") or ()))
            assert key not in seen
            seen.add(key)


def test_vector_store_attributes_are_strings_and_capped():
    for name in kb_registry.approved_files():
        attrs = kb_registry.vector_store_attributes(name)
        assert len(attrs) <= 16 and all(isinstance(v, str) for v in attrs.values())
    assert "institution" not in kb_registry.vector_store_attributes("Arbitration-And-Conciliation-Act-1996.pdf")


def test_metadata_path_env_override(tmp_path, monkeypatch):
    path = tmp_path / "kb.json"
    path.write_text(json.dumps([{"doc_id": "x", "title": "X Rules", "file_name": "x.pdf",
                                 "institution": None, "provision_label": "Article"}]), encoding="utf-8")
    monkeypatch.setenv("KB_METADATA_PATH", str(path))
    kb_registry._records_by_file.cache_clear()
    try:
        assert kb_registry.approved_files() == {"x.pdf", kb_registry.SOP_FILE}
        assert kb_registry.provision_label("x.pdf") == "Article"
    finally:
        monkeypatch.delenv("KB_METADATA_PATH")
        kb_registry._records_by_file.cache_clear()


def _act(doc_id, file_name, status):
    return {"doc_id": doc_id, "title": "Arbitration and Conciliation Act, 1996", "file_name": file_name,
            "institution": None, "doc_type": "statute", "status": status, "provision_label": "Section"}


def test_in_force_and_superseded_records_over_two_files(tmp_path, monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    recs = [_act("act-old", "act-2019.pdf", "superseded"), _act("act-new", "act-2026.pdf", "in_force"),
            {"doc_id": "d1", "title": "D (A) Rules", "file_name": "d.pdf", "institution": "D Centre (D)",
             "status": "in_force", "page_range": [1, 5]},
            {"doc_id": "d2", "title": "D (B) Rules", "file_name": "d.pdf", "institution": "D Centre (D)",
             "status": "in_force", "page_range": [6, 9]}]
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(recs), encoding="utf-8")
    monkeypatch.setenv("KB_METADATA_PATH", str(path))
    kb_registry._records_by_file.cache_clear()
    try:
        # 4 records, 3 files (+ SOP): everything counts unique file names.
        assert kb_registry.approved_files() == {"act-2019.pdf", "act-2026.pdf", "d.pdf", kb_registry.SOP_FILE}
        assert kb_registry.vector_store_attributes("act-2019.pdf")["status"] == "superseded"
        assert kb_registry.vector_store_attributes("act-2026.pdf")["status"] == "in_force"
        assert kb_registry.search_filter(kb_registry.ACT)["filters"][0]["value"] == "act-new"
        assert kb_registry.excluded(kb_registry.records_for_file("act-2019.pdf")[0], "Section 11")

        spec = importlib.util.spec_from_file_location(
            "setup_ai_knowledge", kb_registry.Path(kb_registry.__file__).parent / "scripts" / "setup_ai_knowledge.py")
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        assert len(setup.SOURCE_NAMES) == 4
        expected = setup.SOURCE_ATTRIBUTES
        # The old Act was indexed while in force: a status change alone must trigger an update.
        store = {"act-2019.pdf": SimpleNamespace(id="f1", attributes={**expected["act-2019.pdf"], "status": "in_force"}),
                 "act-2026.pdf": SimpleNamespace(id="f2", attributes=dict(expected["act-2026.pdf"])),
                 "stray.pdf": SimpleNamespace(id="f3", attributes={})}
        assert setup.stale_attributes(store, expected) == ["act-2019.pdf"]
        assert setup.unknown_store_files(store, setup.SOURCE_NAMES) == ["stray.pdf"]
        updates = []
        client = SimpleNamespace(vector_stores=SimpleNamespace(files=SimpleNamespace(
            update=lambda **kw: updates.append(kw))))
        setup.update_attributes(client, "vs", store, expected)
        assert updates == [{"vector_store_id": "vs", "file_id": "f1", "attributes": expected["act-2019.pdf"]}]
    finally:
        monkeypatch.delenv("KB_METADATA_PATH")
        kb_registry._records_by_file.cache_clear()
