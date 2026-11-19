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
                                 "institution": None, "provision_label": "Article", "jurisdiction": "India"}]),
                    encoding="utf-8")
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
            "institution": None, "doc_type": "statute", "status": status, "provision_label": "Section",
            "jurisdiction": "India"}


def test_in_force_and_superseded_records_over_two_files(tmp_path, monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    recs = [_act("act-old", "act-2019.pdf", "superseded"), _act("act-new", "act-2026.pdf", "in_force"),
            {"doc_id": "d1", "title": "D (A) Rules", "file_name": "d.pdf", "institution": "D Centre (D)",
             "status": "in_force", "page_range": [1, 5], "jurisdiction": "Delhi"},
            {"doc_id": "d2", "title": "D (B) Rules", "file_name": "d.pdf", "institution": "D Centre (D)",
             "status": "in_force", "page_range": [6, 9], "jurisdiction": "Delhi"}]
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


# ---- jurisdiction ----------------------------------------------------------

def test_shipped_records_carry_their_jurisdiction():
    """The Act and its amendments: India. Institutional rules: the institution's own seat."""
    want = {"ACT": "India", "DIAC": "Delhi", "ICA": "Delhi", "MCIA": "Mumbai", "SIAC": "Singapore",
            "ICC": "Paris", "LCIA": "London"}
    for recs in kb_registry._records_by_file().values():
        for rec in recs:
            assert rec["jurisdiction"] == want[kb_registry.record_code(rec)], rec["doc_id"]


def _load(tmp_path, monkeypatch, records, keep=False):
    """Load `records` as the registry; returns (records by file, load error)."""
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(records) if not isinstance(records, str) else records, encoding="utf-8")
    monkeypatch.setenv("KB_METADATA_PATH", str(path))
    kb_registry._records_by_file.cache_clear()
    try:
        return kb_registry._records_by_file(), kb_registry.load_error()
    finally:
        if not keep:
            monkeypatch.delenv("KB_METADATA_PATH")
            kb_registry._records_by_file.cache_clear()


def _judgment(court, jurisdiction):
    return {"doc_id": "j1", "title": "A v B", "file_name": "j1.pdf", "institution": None, "doc_type": "judgment",
            "court": court, "jurisdiction": jurisdiction}


@pytest.mark.parametrize("court,jurisdiction", [("Supreme Court of India", "India"), ("Delhi High Court", "Delhi")])
def test_a_judgment_takes_its_courts_jurisdiction(tmp_path, monkeypatch, court, jurisdiction):
    records, error = _load(tmp_path, monkeypatch, [_judgment(court, jurisdiction)])
    assert error is None and records["j1.pdf"][0]["jurisdiction"] == jurisdiction


@pytest.mark.parametrize("record,message", [
    (_judgment("Delhi High Court", "India"), "expected 'Delhi'"),
    (_judgment("Bombay High Court", "Maharashtra"), "add it to COURT_JURISDICTIONS"),
    ({**_act("a", "a.pdf", "in_force"), "jurisdiction": "Delhi"}, "expected 'India'"),
    ({"doc_id": "m", "title": "MCIA Rules", "file_name": "m.pdf", "doc_type": "institutional_rules",
      "institution": "Mumbai Centre for International Arbitration (MCIA)", "jurisdiction": "India"}, "expected 'Mumbai'"),
    ({k: v for k, v in _act("a", "a.pdf", "in_force").items() if k != "jurisdiction"}, "missing jurisdiction"),
    ({**_act("a", "a.pdf", "in_force"), "jurisdiction": "  "}, "missing jurisdiction"),
])
def test_a_wrong_or_missing_jurisdiction_fails_the_load_without_raising(tmp_path, monkeypatch, record, message):
    records, error = _load(tmp_path, monkeypatch, [record])
    assert records == {} and message in error


def test_an_institution_not_listed_yet_needs_only_a_jurisdiction(tmp_path, monkeypatch):
    rec = {"doc_id": "h", "title": "HKIAC Rules", "file_name": "h.pdf", "doc_type": "institutional_rules",
           "institution": "Hong Kong International Arbitration Centre (HKIAC)", "jurisdiction": "Hong Kong"}
    records, error = _load(tmp_path, monkeypatch, [rec])
    assert error is None and records["h.pdf"][0]["jurisdiction"] == "Hong Kong"


def test_a_bad_kb_file_disables_the_chatbot_and_nothing_else(tmp_path, monkeypatch, caplog):
    import asyncio
    from fastapi import HTTPException
    import ai_chat
    import llm_service
    monkeypatch.setattr(llm_service, "AI_MODEL", "test-model")
    monkeypatch.setattr(llm_service, "_provider_key", lambda: "key")
    try:
        with caplog.at_level("CRITICAL", logger="kb_registry"):
            records, error = _load(tmp_path, monkeypatch, [{**_act("a", "a.pdf", "in_force"), "jurisdiction": "Delhi"}],
                                   keep=True)
        assert records == {} and "expected 'India'" in error
        assert any("Instant Legal Help is DISABLED" in r.message for r in caplog.records)
        assert not llm_service.is_configured()
        for message in ("hi", "What does Section 21 of the Arbitration Act say?"):  # small talk is refused too
            with pytest.raises(HTTPException) as e:
                asyncio.run(ai_chat.handle_chat_message(None, None, message, None, client_ip="203.0.113.80"))
            assert e.value.status_code == 503
    finally:
        monkeypatch.delenv("KB_METADATA_PATH")
        kb_registry._records_by_file.cache_clear()
    assert kb_registry.load_error() is None and llm_service.is_configured()


@pytest.mark.parametrize("content", ["not json", json.dumps([{"doc_id": "x", "title": "X"}])])  # unreadable / no file_name
def test_an_unreadable_kb_file_also_only_disables_the_chatbot(tmp_path, monkeypatch, content):
    records, error = _load(tmp_path, monkeypatch, content)
    assert records == {} and error


def test_every_chatbot_module_imports_with_a_bad_kb_file(tmp_path):
    """What startup seeding imports: none of it may raise when the KB metadata is bad."""
    import os
    import subprocess
    import sys
    path = tmp_path / "kb.json"
    path.write_text(json.dumps([{**_act("a", "a.pdf", "in_force"), "jurisdiction": "Delhi"}]), encoding="utf-8")
    code = ("import ai_chat, chat_drafts, chat_uploads, llm_service, prompt_builder, rag_provisions, kb_registry; "
            "print('LOAD_ERROR', kb_registry.load_error())")
    run = subprocess.run([sys.executable, "-c", code], cwd=kb_registry.Path(kb_registry.__file__).parent,
                         env={**os.environ, "KB_METADATA_PATH": str(path)}, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    assert "LOAD_ERROR kb.json: KB record a: jurisdiction 'Delhi', expected 'India'" in run.stdout
