import json

import pytest

import kb_registry

DIAC = "DIAC Rules conclusive_UsingOCR.pdf"


def test_loads_all_files_plus_sop():
    files = kb_registry.approved_files()
    assert len(files) == 8 and kb_registry.SOP_FILE in files
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
