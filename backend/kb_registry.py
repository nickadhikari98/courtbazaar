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
        out.append((key, rule_set_title(rec)))
    return tuple(out)


# ---- Institutions: the one place their names/aliases live ----------------
ACT = "ACT"
# code -> words that name it in a question. ACT is the Arbitration and Conciliation Act.
INSTITUTION_ALIASES = {
    "DIAC": r"\bdiac\b|delhi international arbitration cent(?:re|er)",
    "ICA": r"\bica\b|indian council of arbitration",
    "MCIA": r"\bmcia\b|mumbai cent(?:re|er) for international arbitration",
    "SIAC": r"\bsiac\b|singapore international arbitration cent(?:re|er)",
    "ICC": r"\bicc\b|international chamber of commerce",
    "LCIA": r"\blcia\b|london court of international arbitration",
    ACT: r"\barbitration (?:and conciliation )?act\b|\ba\s*&\s*c act\b|\b(?:sections?|sec\.?|s\.)\s*\d{1,3}[a-z]?\b",
}
_ALIAS_RES = {code: re.compile(rx, re.IGNORECASE) for code, rx in INSTITUTION_ALIASES.items()}


def detect_institutions(query: str) -> set:
    """Every institution (and ACT) the question names."""
    return {code for code, rx in _ALIAS_RES.items() if rx.search(query or "")}


def record_code(rec: dict) -> Optional[str]:
    m = re.search(r"\((\w+)\)$", rec.get("institution") or "")
    if m:
        return m.group(1)
    return ACT if rec.get("doc_type") == "statute" else None


def files_for(code: str) -> list:
    """Files for one institution that still hold an in-force document; a
    superseded file (e.g. the 2019 Act text) must not compete in routing."""
    return [f for f, recs in _records_by_file().items()
            if record_code(recs[0]) == code and any(r.get("status") == "in_force" for r in recs)]


def code_for_file(filename: str) -> Optional[str]:
    recs = records_for_file(filename)
    return record_code(recs[0]) if recs else None


def all_codes() -> set:
    return {c for c in map(code_for_file, _records_by_file()) if c}


def search_filter(code: str) -> Optional[dict]:
    """OpenAI attribute filter for one institution. Bundled PDFs (DIAC, ICC)
    carry only their first set's doc_id, so institutions filter on
    `institution`; only the Act (no institution) filters on doc_id. Never
    matches a file not tagged in_force."""
    recs = [r for f in files_for(code) for r in records_for_file(f)]
    if not recs:
        return None
    first = next((r for r in recs if r.get("status") == "in_force"), recs[0])  # never a superseded doc_id
    key, value = ("doc_id", first["doc_id"]) if code == ACT else ("institution", first["institution"])
    return {"type": "and", "filters": [{"type": "eq", "key": key, "value": value},
                                       {"type": "eq", "key": "status", "value": "in_force"}]}


def search_name(filename: str) -> str:
    """Status-line name: "DIAC Rules", "the SOP", the Act's title."""
    if filename == SOP_FILE:
        return "the SOP"
    code = code_for_file(filename)
    if code and code != ACT:
        return f"{code} Rules"
    recs = records_for_file(filename)
    return recs[0]["title"] if recs else filename


def rule_set_title(rec: dict) -> str:
    """Full rule-set title with its year: "ICC Arbitration Rules 2026"."""
    # Only "DIAC (X) Rules" is spelled out (KB_INSTRUMENT_URLS keys); "ICC Arbitration Rules" stays short.
    title = _full_title(rec["title"], rec.get("institution")) if "(" in rec["title"] else rec["title"]
    version = str(rec.get("document_version") or "")
    return f"{title} {version}" if re.fullmatch(r"\d{4}", version) and version not in title else title


# Our own R2 copy is never a citation link (ICC, SIAC, LCIA, MCIA, ICA texts are copyrighted).
_R2_HOST_RE = re.compile(r"^https://[^/]*(?:\.r2\.dev|\.r2\.cloudflarestorage\.com)(?:/|$)", re.IGNORECASE)


def official_url(filename: str, set_title: Optional[str] = None) -> Optional[str]:
    """The publisher's own link for a rule set (the record whose
    rule_set_title starts `set_title`, else the file's only record), or None."""
    recs = records_for_file(filename) or []
    rec = next((r for r in recs if set_title and set_title.startswith(rule_set_title(r))), None)
    rec = rec or (recs[0] if len(recs) == 1 else None)
    url = (rec or {}).get("official_url")
    return url if isinstance(url, str) and url.startswith("https://") and not _R2_HOST_RE.match(url) else None


def rule_set_for_page(filename: str, page: int) -> Optional[dict]:
    for rec in records_for_file(filename) or []:
        lo, hi = (rec.get("page_range") or [0, 10 ** 6])[:2]
        if lo <= page <= hi:
            return rec
    return None


def excluded(rec: Optional[dict], query: str) -> bool:
    """A rule set that must not answer this question: not in force, or a
    mediation set answering a question that isn't about mediation."""
    if rec is None:
        return False
    if rec.get("status") != "in_force":
        return True
    return "mediation" in (rec.get("doc_type") or "") and not re.search(r"mediat", query or "", re.IGNORECASE)


def institution_names() -> dict:
    """{"MCIA": ["Mumbai Centre for International Arbitration"], ...} from the
    records' own "Name (ACRONYM)" institution field."""
    names: dict = {}
    for filename in approved_files():
        for rec in records_for_file(filename) or []:
            m = re.match(r"(.+?)\s*\(([A-Z]{2,6})\)$", rec.get("institution") or "")
            if m and m.group(1) not in names.setdefault(m.group(2), []):
                names[m.group(2)].append(m.group(1))
    return names
