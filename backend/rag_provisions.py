"""Rebuilds complete numbered provisions around retrieved vector-store chunks.

Why: the approved DIAC Rules PDF is OCR'd and chunked by the vector store, so
a provision is often split across chunks, and across a page break. Rule 33.1's
"Unless the Centre directs otherwise, 50% ... payable by the Claimant" sits
on the page after its "33.1" number, in a different chunk from it. Given only
the chunks, the model either dropped that sentence or couldn't tell which rule
it belonged to.

How: for a chunk that came from an approved file (the caller has already
checked filename and source metadata), fetch that same file's parsed text
from the same vector store (`vector_stores.files.content`, scoped to the
configured store, so nothing outside the approved documents can be read),
parse it into numbered provisions, find where the chunk sits, and hand the
model the complete provision(s) the chunk overlaps, each labelled with its
own rule number. Unnumbered text is attached to a rule only through the
document's own structure: it belongs to the last numbered provision before
it, with only page breaks in between. Anything that can't be located falls
back to the raw chunk.
"""
import contextvars
import logging
import math
import re
import time

import kb_registry
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# "<IMAGE FOR PAGE: 33 / 51>" / "<PARSED TEXT FOR PAGE: 34 / 51>"
PAGE_MARKER_RE = re.compile(r"<(?:IMAGE|PARSED TEXT) FOR PAGE:\s*(\d+)\s*/\s*\d+>")
# A numbered provision at the start of a line: "33. Advance on Costs", "33.1 The Centre",
# "11A. Qualifications" (the Act), "Article 9B" / "Rule 14.2" (rules that print the word).
_PROVISION_START_RE = re.compile(
    r"(?m)(?:^|(?<=\[))((?:Article|Rule)\s+)?(\d{1,3})([A-Z]?)(?:\.(\d{1,2}))?\.?\s+(?=[A-Z(\"'])")
# Rules that print the word on every heading (ICC, LCIA "Article 31 ...") also
# run headings into the previous text ("... in Appendix IV. Article 32 Expedited"),
# and two-column pages put one column's "9.8" after the other's text and a gutter (LCIA).
_WORD_PROVISION_START_RE = re.compile(
    r"(?m)(?:^|(?<=[.:;]\s)|(?<= {3}))((?:Article|Rule)\s+)?(\d{1,3})([A-Z]?)(?:\.(\d{1,2}))?\.?\s+(?=[A-Z(\"'])")
# The heading above a sub-part's first provision, whose numbering restarts:
# "APPENDIX IV - EMERGENCY ..." (ICC), "SCHEDULE 1. EMERGENCY ..." (SIAC), "APPENDIX - FEES AND COSTS" (ICC Mediation).
_APPENDIX_RE = re.compile(
    r"\b(APPENDIX|SCHEDULE|ANNEX)(?: ([IVX]+|\d{1,2}))?\s*[-.:]\s*([A-Z][A-Z ,'&-]*[A-Z])\b"
    r"|\bSchedule of Fees\s+Part ([IVX]+)\.")
# How a document names an item of its own sub-part: "paragraph 7 of this Schedule 1", "Article 3 of this Appendix".
_PART_ITEM_RE = r"\b(Article|Paragraph|Rule|Section)s?\s+\d{{1,3}}\S*\s+of\s+(?:this\s+|the\s+)?{kind}\b"
# An amended statute's footnote, numbered from 1 on every page: "Subs. by Act 33 of 2019",
# "Ins. by ...", "The words “a company or” omitted by s. 2, ibid.".
_AMENDMENT_NOTE_RE = re.compile(
    r"(?:(?:Subs|Ins|Rep)\.|Substituted|Inserted|Omitted|Added|Renumbered)\s+by\b"
    r"|The (?:words?|proviso|figures|brackets|Explanation)\b[^\n]{0,200}?\b(?:omitted|subs\.|substituted|ins\.|inserted) by\b"
    r"|[^\n]*?\b(?:w\.e\.f\.|ibid\.)")  # "S. 9 shall be renumbered ... s. 5, Act 3 of 2016 (w.e.f. 23-10-2015)"
_SMALL_WORDS = {"Of", "The", "And", "For", "To", "In", "On"}
# "[Source: <file> | Rule 33.1]" / "| Article 9B" / "| Section 11A" / "| Paragraph 3" block label written by expand_chunks.
_BLOCK_LABEL_RE = re.compile(
    r"(?m)^\[Source: [^\]|]+\| (?:Rule|Article|Section|Paragraph) (\d{1,3}[A-Z]?(?:\.\d{1,2})?)(?: \| [^\]\n]*)?\]\n")
# "Section 11", "Rule 14.2", "Article 9B" named in a question.
EXACT_REF_RE = re.compile(
    r"\b(Rule|Article|Section|Sec\b\.?|S\.)s?\s*(\d{1,3}[A-Za-z]?(?:\.\d{1,2})?)\b", re.IGNORECASE)
_LABEL_WORDS = {"rule": "Rule", "article": "Article"}  # anything else matched is a Section spelling

MAX_BLOCKS = 14
MAX_CONTEXT_CHARS = 20000
# Characters of this turn's prompt that come out of the same budget (a matter's
# custom instructions, chat_matters); set per turn by ai_chat.
RESERVED_CHARS: "contextvars.ContextVar[int]" = contextvars.ContextVar("reserved_context_chars", default=0)


def context_char_budget() -> int:
    return max(0, MAX_CONTEXT_CHARS - RESERVED_CHARS.get())

_doc_cache: Dict[Tuple[str, str], Tuple[float, str]] = {}
# doc text -> [(offset, page number)], to match a provision to its rule set's page_range.
_page_index: Dict[str, List[Tuple[int, int]]] = {}


def clear_cache() -> None:
    _doc_cache.clear()
    _page_index.clear()


def exact_refs(query: str) -> List[Tuple[str, str]]:
    """[("Section", "11A"), ...] the question names, label capitalised."""
    return [(_LABEL_WORDS.get(m.group(1).lower(), "Section"), m.group(2).upper())
            for m in EXACT_REF_RE.finditer(query or "")]


def _index_pages(raw: str, text: str, normalize) -> List[Tuple[int, int]]:
    """Where each page starts in the normalized text, found from the page's
    first long line. shortcut: a page whose first lines are all short is
    placed at its first long line (a few lines late); fine for page_range."""
    out: List[Tuple[int, int]] = []
    marks = list(PAGE_MARKER_RE.finditer(raw))
    pos = 0
    for i, m in enumerate(marks):
        page_text = normalize(raw[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(raw)])
        probe = next((ln[:120] for ln in page_text.split("\n") if len(ln) >= 30), None)
        at = text.find(probe, pos) if probe else -1
        if at >= 0:
            out.append((at, int(m.group(1))))
            pos = at
    return out


def page_at(pages: List[Tuple[int, int]], offset: int) -> Optional[int]:
    page = None
    for start, number in pages:
        if start > offset:
            break
        page = number
    return page


async def approved_document_text(client, vector_store_id: str, file_id: str, normalize,
                                 ttl_seconds: float) -> Optional[str]:
    """Parsed text of one file in the configured vector store, normalized
    with `normalize` (llm_service._readable_excerpt) and cached in-process.
    None if the store won't return it: callers then use the raw chunks."""
    key = (vector_store_id, file_id)
    cached = _doc_cache.get(key)
    if cached and time.monotonic() - cached[0] < ttl_seconds:
        return cached[1]
    parts: List[str] = []
    page = await client.vector_stores.files.content(file_id, vector_store_id=vector_store_id)
    async for part in page:
        value = getattr(part, "text", None)
        if value:
            parts.append(value)
    if not parts:
        return None
    raw = "\n".join(parts)
    text = normalize(PAGE_MARKER_RE.sub("\n", raw))
    _doc_cache[key] = (time.monotonic(), text)
    _page_index[text] = _index_pages(raw, text, normalize)
    return text


def _instrument_title(doc: str, start: int) -> str:
    """The upper-case title lines just above an instrument's first provision,
    e.g. "DELHI INTERNATIONAL ARBITRATION CENTRE (ADMINISTRATIVE COSTS &
    ARBITRATORS' FEES) RULES, 2018". Empty if the document has none there."""
    collected: List[str] = []
    for line in reversed(doc[max(0, start - 800):start].split("\n")):
        letters = [c for c in line if c.isalpha()]
        if len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
            collected.append(line.strip())
        elif collected:
            break
        if len(collected) == 4:
            break
    return re.sub(r"[\]|]", "", " ".join(reversed(collected)))[:160]


def _num(key: Tuple[int, str]) -> str:
    return f"{key[0]}{key[1]}"


def _appendix(doc: str, start: int) -> Optional[str]:
    """"Appendix IV - Emergency Arbitrator Provisions", "Schedule 1 - Emergency
    Arbitrator Procedure" (or "Schedule of Fees, Part II") when the heading
    just above an instrument's first provision names one, else None."""
    found = list(_APPENDIX_RE.finditer(doc[max(0, start - 200):start]))
    if not found:
        return None
    if found[-1].group(4):
        return f"Schedule of Fees, Part {found[-1].group(4)}"
    words = found[-1].group(3).title().split()
    name = " ".join([words[0]] + [w.lower() if w in _SMALL_WORDS else w for w in words[1:]])
    number = f" {found[-1].group(2)}" if found[-1].group(2) else ""
    return f"{found[-1].group(1).title()}{number} - {name}"


def part_word(doc: str, appendix: str, default: str) -> str:
    """What the document calls an item of this sub-part, from its own cross
    references ("paragraph 7 of this Schedule 1" -> "Paragraph"); `default`
    (the file's provision_label) when it never says."""
    kind = appendix.split()[0]
    found = [m.group(1).title() for m in re.finditer(_PART_ITEM_RE.format(kind=kind), doc, re.IGNORECASE)]
    return max(set(found), key=found.count) if found else default


def _running_lines(doc: str) -> set:
    """Page headers/footers: lines that, without their digits, repeat 3+
    times ("42   Arbitration Rules of the Singapore ... SIAC Rules"). A page
    number at the start of one is not a provision heading."""
    counts: Dict[str, int] = {}
    for line in doc.split("\n"):
        key = " ".join(re.sub(r"\d", "", line).split())
        if len(key) >= 20:
            counts[key] = counts.get(key, 0) + 1
    return {k for k, n in counts.items() if n >= 3}


def parse_provisions(doc: str, word: Optional[str] = None) -> List[Dict[str, Any]]:
    """Numbered provisions in document order: number, parent, instrument,
    appendix, start, end, text. A sub-rule ("33.1") counts only under its own
    parent heading ("33."); a top-level number restarting at 1 begins a new
    instrument (the PDF holds more than one set of rules, so numbers repeat).
    Other line-initial numbers (schedule rows, amounts) are ignored. With
    `word` ("Article"), a top-level heading must print it: a bare "7 The
    Order ..." is then a paragraph of the article (ICC), or a page number."""
    accepted: List[Dict[str, Any]] = []
    parent: Optional[Tuple[int, str]] = None  # (11, "A") for "11A": sorts between 11 and 12
    prev_parent: Optional[Tuple[int, str]] = None
    parent_has_subs = False
    instrument = 0
    titles: Dict[int, str] = {}
    appendices: Dict[int, Optional[str]] = {}
    running = _running_lines(doc)
    for m in (_WORD_PROVISION_START_RE if word else _PROVISION_START_RE).finditer(doc):
        if word and m.group(4) is None and (m.group(1) or "").strip() != word:
            continue
        line_end = doc.find("\n", m.start())
        if _AMENDMENT_NOTE_RE.match(doc, m.end()):
            continue  # a statute's page footnote ("1. Subs. by Act 33 of 2019, s. 2"), not a section
        # Only an undotted number ("42   Arbitration Rules ..."): "3. Inserted by ..." footnotes repeat too.
        if "." not in m.group(0) and " ".join(re.sub(r"\d", "", doc[m.start():line_end if line_end >= 0 else len(doc)]).split()) in running:
            continue
        top, sub = int(m.group(2)), m.group(4)
        key = (top, m.group(3))
        # After a column gutter only a paragraph of the open (or next) article counts: the other
        # column can run ahead ("Article 14" beside "Article 13") and must not move numbering on.
        # shortcut: interleaved columns still lose a few LCIA paragraphs (10.4, 23.1); re-index LCIA single-column to fix.
        if doc[max(0, m.start() - 3):m.start()] == "   " and not (
                sub is not None and parent is not None and (top == parent[0] or (top == parent[0] + 1 and sub == "1"))):
            continue
        if sub is not None:
            if parent != key:
                if (key == prev_parent and not parent_has_subs and accepted
                        and accepted[-1]["number"] == _num(parent)):
                    # The "parent" heading was a false start: OCR put a page
                    # number at a line start ("the 9.\n9 Respondent shall
                    # ...") and the previous rule carries on (8.6 after it).
                    # Undo it, so its text stays with the rule it belongs to.
                    accepted.pop()
                    parent, prev_parent = prev_parent, None
                    parent_has_subs = True
                elif parent is not None and not key[1] and top == parent[0] + 1 and int(sub) == 1:
                    # The next rule's own heading line is missing (OCR ran it
                    # into the previous text), but its first sub-rule is
                    # there: "9.1" right after rule 8 opens rule 9.
                    prev_parent, parent, parent_has_subs = parent, key, False
                elif parent is not None and parent[0] == top and parent[1] and not key[1]:
                    pass  # "9.8" under "Article 9B": LCIA numbers Articles 9A-9C's paragraphs 9.1-9.19
                else:
                    continue
            number = f"{_num(key)}.{int(sub)}"
            parent_has_subs = True
        else:
            if parent is not None and key == (1, "") and parent[0] > 1:
                instrument += 1
            elif parent is not None and not (parent < key and top <= parent[0] + 20):
                continue  # numbering only moves forward (gaps allowed); anything else isn't a rule heading
            prev_parent, parent, parent_has_subs = parent, key, False
            number = _num(key)
        if instrument not in titles:
            titles[instrument] = _instrument_title(doc, m.start())
            appendices[instrument] = _appendix(doc, m.start())
        accepted.append({"number": number, "parent": _num(parent), "instrument": instrument,
                         "title": titles[instrument], "appendix": appendices[instrument], "start": m.start()})
    for i, p in enumerate(accepted):
        p["end"] = accepted[i + 1]["start"] if i + 1 < len(accepted) else len(doc)
        p["text"] = doc[p["start"]:p["end"]].strip()
    return accepted


def locate(chunk: str, doc: str) -> Optional[Tuple[int, int]]:
    """Span of `chunk` (already normalized like `doc`) inside `doc`, found
    from its longest full lines (a chunk's first and last lines may be cut)."""
    lines = sorted((ln for ln in chunk.split("\n") if len(ln) >= 30), key=len, reverse=True)
    for probe in lines[:3]:
        key = probe[:200]
        at = doc.find(key)
        if at >= 0 and doc.find(key, at + 1) < 0:  # unique match only
            start = max(0, at - chunk.find(key))
            return start, min(len(doc), start + len(chunk))
    return None


_KEYWORD_RE = re.compile(r"[a-z]{3,}")
_KEYWORD_STOPWORDS = frozenset("""
the and for are was were who what when where why how can does did will shall may must not any all such with from
this that these those which about under into have has had their its his her they them there then than but
""".split())
BM25_K1, BM25_B = 1.5, 0.75


def _keywords(text: str) -> List[str]:
    return [w.rstrip("s") for w in _KEYWORD_RE.findall(text.lower()) if w not in _KEYWORD_STOPWORDS]


def keyword_matches(query: str, provisions: List[Dict[str, Any]], limit: int = 3) -> List[int]:
    """Indices of the provisions that best match the query's words (BM25),
    best first. Finds what embeddings miss: a rule that shares the question's
    terms but not its meaning ("deposit not paid" -> Rule 33.5)."""
    terms = set(_keywords(query))
    docs = [_keywords(p["text"]) for p in provisions]
    if not terms or not docs:
        return []
    average = sum(map(len, docs)) / len(docs)
    frequency = {t: sum(t in d for d in docs) for t in terms}
    scores = []
    for i, doc in enumerate(docs):
        score = 0.0
        for t in terms:
            hits = doc.count(t)
            if hits:
                idf = math.log(1 + (len(docs) - frequency[t] + 0.5) / (frequency[t] + 0.5))
                score += idf * hits * (BM25_K1 + 1) / (hits + BM25_K1 * (1 - BM25_B + BM25_B * len(doc) / average))
        if score:
            scores.append((score, i))
    return [i for _, i in sorted(scores, reverse=True)[:limit]]


MAX_SUBRULES_PER_HEADING = 8
_HEADING_ONLY_CHARS = 80


def _with_rule_body(provisions: List[Dict[str, Any]], hits: List[int]) -> List[int]:
    """A keyword hit on a bare heading ("33. Advance on Costs") stands for its
    sub-rules, where the actual text is (Rule 33.1's 50/50 split was being cut
    by MAX_BLOCKS while the empty heading took a slot). A short top-level entry
    with no sub-rules is a table-of-contents line ("33 Advance on Costs 28") and
    is dropped; any other hit is kept as is."""
    out: List[int] = []
    for i in hits:
        p = provisions[i]
        if p["number"] != p["parent"] or len(p["text"]) >= _HEADING_ONLY_CHARS:
            out.append(i)
            continue
        subs = [k for k in range(i + 1, len(provisions))
                if provisions[k]["instrument"] == p["instrument"] and provisions[k]["parent"] == p["number"]
                and provisions[k]["number"] != p["number"]][:MAX_SUBRULES_PER_HEADING]
        if subs:
            out.extend([i] + subs)
    return list(dict.fromkeys(out))


def _blocked_indices(filename: str, provisions: List[Dict[str, Any]], doc: Optional[str], query: str,
                     pages: Optional[List[Tuple[int, int]]]) -> Tuple[set, bool]:
    """Titles each provision with its rule set (by page_range in a bundled
    PDF, else the file's one set) and returns the provisions that must not be
    used (kb_registry.excluded), plus whether unplaceable text is unsafe (the
    file holds a set this question must not see)."""
    recs = kb_registry.records_for_file(filename) or []
    unsafe = any(kb_registry.excluded(r, query) for r in recs)
    pages = pages if pages is not None else _page_index.get(doc or "", [])
    blocked = set()
    for k, p in enumerate(provisions):
        if len(recs) == 1:
            rec = recs[0]
        else:
            page = page_at(pages, p["start"]) if pages else None
            rec = kb_registry.rule_set_for_page(filename, page) if page else None
        if rec:
            # An appendix restarts at Article 1, so it is its own set: "..., Appendix IV - ...".
            p["title"] = kb_registry.rule_set_title(rec) + (f", {p['appendix']}" if p.get("appendix") else "")
        if kb_registry.excluded(rec, query) or (rec is None and unsafe):
            blocked.add(k)
    return blocked, unsafe


def _introducing(provisions: List[Dict[str, Any]], i: int, blocked: set) -> List[int]:
    """For an appendix/schedule provision, the main-rules provision that
    brings the sub-part in ("... Provisions in Appendix IV." is ICC Article
    31; "... set out in Schedule 1" is SIAC Rule 12.1): it states when the
    sub-part applies, so it goes in first."""
    m = re.match(r"((?:Appendix|Schedule|Annex) \w+) - ", provisions[i].get("appendix") or "")
    if not m:
        return []
    rx = re.compile(rf"\bin {m.group(1)}\b")
    return [k for k, p in enumerate(provisions)
            if k not in blocked and p.get("appendix") is None and rx.search(p["text"])][:1]


def expand_chunks(filename: str, chunks: List[str], doc: Optional[str], query: str = "",
                  pages: Optional[List[Tuple[int, int]]] = None, share: int = 1) -> List[str]:
    """Context blocks for one approved file: the complete provisions the
    retrieved chunks overlap (plus each one's parent heading), in document
    order and labelled with their provision numbers ("Rule 33.1", "Section
    11A", "Article 9B"); raw chunks where no provision could be located.
    A provision the question names exactly, then those matching its words,
    come first, so the block cap can't push them out. `pages` is
    [(offset, page)] for `doc`; by default the index built when it was fetched.
    `share`: how many files split the context, so each gets its own best
    1/share of the block and character caps (a second institution in a
    comparison was getting none)."""
    label = kb_registry.provision_label(filename) or "Rule"
    provisions = parse_provisions(doc, "Article" if label == "Article" else None) if doc else []
    blocked, unsafe = _blocked_indices(filename, provisions, doc, query, pages)
    named = {num for word, num in exact_refs(query) if word == label}
    exact = [k for k, p in enumerate(provisions) if p["number"] in named]
    chosen: List[int] = []
    raw: List[str] = []
    keyword_hits = [(i, None) for i in _with_rule_body(provisions, exact + keyword_matches(query, provisions))
                    if i not in blocked]
    for i, chunk in keyword_hits + [(None, c) for c in chunks]:
        span = locate(chunk, doc) if provisions and chunk else None
        hits = [i] if i is not None else [
            k for k, p in enumerate(provisions) if span and p["start"] < span[1] and p["end"] > span[0]]
        if not hits:
            if not unsafe:
                raw.append(chunk)
            continue
        hits = [k for k in hits if k not in blocked]
        for i in hits:
            # The rule's own heading ("33. Advance on Costs") gives sub-rules their context.
            head = next((j for j in range(i, -1, -1) if provisions[j]["number"] == provisions[i]["parent"]
                         and provisions[j]["instrument"] == provisions[i]["instrument"]), None)
            for j in _introducing(provisions, i, blocked) + ([head] if head is not None else []) + [i]:
                if j not in chosen:
                    chosen.append(j)
    blocks: List[str] = []
    total = 0
    words: Dict[str, str] = {}
    max_blocks, max_chars = MAX_BLOCKS // max(1, share), context_char_budget() // max(1, share)
    picked: List[Tuple[int, str]] = []
    # The character budget goes in rank order (named, keyword, chunk hits), then blocks
    # print in document order: a long top hit (Act Section 34) is never the one cut.
    for i in chosen[:max_blocks]:
        p = provisions[i]
        title = f" | {p['title']}" if p.get("title") else ""
        # A sub-part's items carry its own word: "Schedule 1, Paragraph 3", "Appendix IV, Article 7".
        word = words.setdefault(p["appendix"], part_word(doc, p["appendix"], label)) if p.get("appendix") else label
        block = f"[Source: {filename} | {word} {p['number']}{title}]\n{p['text']}"
        if total + len(block) <= max_chars:
            picked.append((i, block))
            total += len(block)
    blocks.extend(block for _, block in sorted(picked))
    for chunk in raw:
        block = f"[Source: {filename}]\n{chunk}"
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return blocks


def provision_map(context: str) -> Dict[str, str]:
    """Rule number -> that rule's own text, from the labelled blocks in a
    built context. A top-level rule ("33") also gets the text of its
    sub-rules that are present, since "Rule 33" covers them all."""
    out: Dict[str, List[str]] = {}
    labels = list(_BLOCK_LABEL_RE.finditer(context or ""))
    for i, m in enumerate(labels):
        end = context.find("\n[Source: ", m.end())
        text = context[m.end():end if end >= 0 else len(context)].strip()
        number = m.group(1)
        out.setdefault(number, []).append(text)
        if "." in number:
            out.setdefault(number.split(".")[0], []).append(text)
    return {k: "\n".join(v) for k, v in out.items()}
