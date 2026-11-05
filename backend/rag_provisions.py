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
import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# "<IMAGE FOR PAGE: 33 / 51>" / "<PARSED TEXT FOR PAGE: 34 / 51>"
PAGE_MARKER_RE = re.compile(r"<(?:IMAGE|PARSED TEXT) FOR PAGE:\s*\d+\s*/\s*\d+>")
# A numbered provision at the start of a line: "33. Advance on Costs", "33.1 The Centre".
_PROVISION_START_RE = re.compile(r"(?m)^(\d{1,3})(?:\.(\d{1,2}))?\.?\s+(?=[A-Z(\"'])")
# "[Source: <file> | Rule 33.1]" block label written by expand_chunks.
_BLOCK_LABEL_RE = re.compile(r"(?m)^\[Source: [^\]|]+\| Rule (\d{1,3}(?:\.\d{1,2})?)(?: \| [^\]\n]*)?\]\n")

MAX_BLOCKS = 14
MAX_CONTEXT_CHARS = 20000

_doc_cache: Dict[Tuple[str, str], Tuple[float, str]] = {}


def clear_cache() -> None:
    _doc_cache.clear()


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
    text = normalize(PAGE_MARKER_RE.sub("\n", "\n".join(parts)))
    _doc_cache[key] = (time.monotonic(), text)
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


def parse_provisions(doc: str) -> List[Dict[str, Any]]:
    """Numbered provisions in document order: number, parent, instrument,
    start, end, text. A sub-rule ("33.1") counts only under its own parent
    heading ("33."); a top-level number restarting at 1 begins a new
    instrument (the PDF holds more than one set of rules, so numbers repeat).
    Other line-initial numbers (schedule rows, amounts) are ignored."""
    accepted: List[Dict[str, Any]] = []
    parent: Optional[int] = None
    prev_parent: Optional[int] = None
    parent_has_subs = False
    instrument = 0
    titles: Dict[int, str] = {}
    for m in _PROVISION_START_RE.finditer(doc):
        top, sub = int(m.group(1)), m.group(2)
        if sub is not None:
            if parent != top:
                if (top == prev_parent and not parent_has_subs and accepted
                        and accepted[-1]["number"] == str(parent)):
                    # The "parent" heading was a false start: OCR put a page
                    # number at a line start ("the 9.\n9 Respondent shall
                    # ...") and the previous rule carries on (8.6 after it).
                    # Undo it, so its text stays with the rule it belongs to.
                    accepted.pop()
                    parent, prev_parent = prev_parent, None
                    parent_has_subs = True
                elif parent is not None and top == parent + 1 and int(sub) == 1:
                    # The next rule's own heading line is missing (OCR ran it
                    # into the previous text), but its first sub-rule is
                    # there: "9.1" right after rule 8 opens rule 9.
                    prev_parent, parent, parent_has_subs = parent, top, False
                else:
                    continue
            number = f"{top}.{int(sub)}"
            parent_has_subs = True
        else:
            if parent is not None and top == 1 and parent > 1:
                instrument += 1
            elif parent is not None and not (parent < top <= parent + 20):
                continue  # numbering only moves forward (gaps allowed); anything else isn't a rule heading
            prev_parent, parent, parent_has_subs = parent, top, False
            number = str(top)
        if instrument not in titles:
            titles[instrument] = _instrument_title(doc, m.start())
        accepted.append({"number": number, "parent": str(top), "instrument": instrument,
                         "title": titles[instrument], "start": m.start()})
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


def expand_chunks(filename: str, chunks: List[str], doc: Optional[str], query: str = "") -> List[str]:
    """Context blocks for one approved file: the complete provisions the
    retrieved chunks overlap (plus each one's parent heading), in document
    order and labelled with their rule numbers; raw chunks where no
    provision could be located. Provisions matching the query's words come
    first, so the block cap can't push them out."""
    provisions = parse_provisions(doc) if doc else []
    chosen: List[int] = []
    raw: List[str] = []
    keyword_hits = [(i, None) for i in _with_rule_body(provisions, keyword_matches(query, provisions))]
    for i, chunk in keyword_hits + [(None, c) for c in chunks]:
        span = locate(chunk, doc) if provisions and chunk else None
        hits = [i] if i is not None else [
            k for k, p in enumerate(provisions) if span and p["start"] < span[1] and p["end"] > span[0]]
        if not hits:
            raw.append(chunk)
            continue
        for i in hits:
            # The rule's own heading ("33. Advance on Costs") gives sub-rules their context.
            head = next((j for j in range(i, -1, -1) if provisions[j]["number"] == provisions[i]["parent"]
                         and provisions[j]["instrument"] == provisions[i]["instrument"]), None)
            for j in ([head] if head is not None else []) + [i]:
                if j not in chosen:
                    chosen.append(j)
    blocks: List[str] = []
    total = 0
    for i in sorted(chosen[:MAX_BLOCKS]):
        p = provisions[i]
        title = f" | {p['title']}" if p.get("title") else ""
        block = f"[Source: {filename} | Rule {p['number']}{title}]\n{p['text']}"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        blocks.append(block)
        total += len(block)
    for chunk in raw:
        block = f"[Source: {filename}]\n{chunk}"
        if total + len(block) > MAX_CONTEXT_CHARS:
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
