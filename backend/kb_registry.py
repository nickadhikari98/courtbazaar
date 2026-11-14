"""Approved chatbot knowledge-base files and their metadata.

Arbitration sources come from kb/arbitration_kb_metadata.json (one record per
rule set; a PDF bundling several sets has several records with `page_range`).
The CourtBazaar SOP is internal and has no record there, so it is built here.
"""
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path(__file__).resolve().parent / "kb" / "arbitration_kb_metadata.json"

SOP_FILE = "STANDARD OPERATING PROCEDURE (SOP).docx"
_SOP_META = {"source_id": "court_bazaar_sop", "title": SOP_FILE}
_SOP_LABEL = "Standard Operating Procedure (SOP)"
# Files already indexed before this registry keep the source_id the live
# vector store was tagged with; retrieval rejects chunks whose tag differs.
_LEGACY_SOURCE_IDS = {"DIAC Rules conclusive_UsingOCR.pdf": "diac_rules"}


@lru_cache(maxsize=1)
def _records_by_file() -> dict:
    path = Path(os.environ.get("KB_METADATA_PATH") or _DEFAULT_PATH)
    with path.open(encoding="utf-8") as fh:
        records = json.load(fh)
    by_file: dict = {}
    for record in records:
        by_file.setdefault(record["file_name"], []).append(record)
    for recs in by_file.values():
        recs.sort(key=lambda r: (r.get("page_range") or [0])[0])
    return by_file


def approved_files() -> set:
    return set(_records_by_file()) | {SOP_FILE}


def records_for_file(filename: str) -> Optional[list]:
    return _records_by_file().get(filename)


def file_meta(filename: str) -> Optional[dict]:
    """{source_id, title}: the vector-store attributes retrieval checks."""
    if filename == SOP_FILE:
        return dict(_SOP_META)
    recs = records_for_file(filename)
    if not recs:
        return None
    return {"source_id": _LEGACY_SOURCE_IDS.get(filename, recs[0]["doc_id"]), "title": filename}


def vector_store_attributes(filename: str) -> Optional[dict]:
    """OpenAI file attributes: string values only (the API allows max 16 keys)."""
    meta = file_meta(filename)
    recs = records_for_file(filename)
    if meta is None or not recs:
        return meta
    first = recs[0]
    extra = {k: first.get(k) for k in ("doc_id", "institution", "collection", "doc_type", "status")}
    return {**meta, **{k: v for k, v in extra.items() if isinstance(v, str)}}


def institution(filename: str) -> Optional[str]:
    recs = records_for_file(filename)
    return recs[0].get("institution") if recs else None


def provision_label(filename: str) -> Optional[str]:
    recs = records_for_file(filename)
    return recs[0].get("provision_label") if recs else None


def _full_title(title: str, inst: Optional[str]) -> str:
    # "DIAC (X) Rules" -> "Delhi International Arbitration Centre (X) Rules".
    m = re.match(r"(.+?) \((\w+)\)$", inst or "")
    if m and title.startswith(m.group(2) + " "):
        return m.group(1) + title[len(m.group(2)):]
    return title


def display_label(filename: str) -> Optional[str]:
    if filename == SOP_FILE:
        return _SOP_LABEL
    recs = records_for_file(filename)
    if not recs:
        return None
    if len(recs) > 1 and recs[0].get("institution"):
        return recs[0]["institution"] + " Rules"
    return _full_title(recs[0]["title"], recs[0].get("institution"))


def instruments(filename: str) -> tuple:
    """((match_key, title), ...) for a file bundling several rule sets; () otherwise.

    match_key is the upper-case letters of the first two words that tell the
    sets apart (the bracketed part, or what follows the abbreviation), matched
    against the set title the PDF prints above each provision."""
    recs = records_for_file(filename) or []
    if len(recs) < 2:
        return ()
    out = []
    for rec in recs:
        m = re.search(r"\(([^)]*)\)", rec["title"])
        words = (m.group(1) if m else rec["title"].split(" ", 1)[-1]).split()
        key = re.sub(r"[^A-Z]", "", " ".join(words[:2]).upper())
        out.append((key, _full_title(rec["title"], rec.get("institution"))))
    return tuple(out)
