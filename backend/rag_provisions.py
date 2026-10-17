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
    instrument = 0
    titles: Dict[int, str] = {}
    for m in _PROVISION_START_RE.finditer(doc):
        top, sub = int(m.group(1)), m.group(2)
        if sub is not None:
            if parent != top:
                continue
            number = f"{top}.{int(sub)}"
        else:
            if parent is not None and top == 1 and parent > 1:
                instrument += 1
            elif parent is not None and not (parent < top <= parent + 20):
                continue  # numbering only moves forward (gaps allowed); anything else isn't a rule heading
            parent = top
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


def expand_chunks(filename: str, chunks: List[str], doc: Optional[str]) -> List[str]:
    """Context blocks for one approved file: the complete provisions the
    retrieved chunks overlap (plus each one's parent heading), in document
    order and labelled with their rule numbers; raw chunks where no
    provision could be located."""
    provisions = parse_provisions(doc) if doc else []
    chosen: List[int] = []
    raw: List[str] = []
    for chunk in chunks:
        span = locate(chunk, doc) if provisions else None
        hits = [i for i, p in enumerate(provisions) if span and p["start"] < span[1] and p["end"] > span[0]]
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
