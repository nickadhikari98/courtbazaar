"""Deterministic output grounding and safety checks for Instant Legal Help.

Every reply the model writes passes through here before it is stored or
shown, following SOURCE -> EVIDENCE -> CLAIM -> FINAL ANSWER:

- validate_grounded_answer: for answers built on retrieved document text or
  live tool data, every hallucination-prone claim (numbers, prices, dates,
  sections, counts, counsel names, pricing/policy qualifiers such as
  "includes" or "refundable") must appear in that evidence. Unsupported
  clauses are cut, unsupported sentences dropped, and if too little
  survives, the caller falls back to its safe "couldn't verify" reply.
- guard_general_answer: for answers from general model knowledge, no
  CourtBazaar-specific facts (there is no CourtBazaar evidence on these
  turns), no case citations or long quotations (which can't be verified),
  and legal figures are qualified as unverified — confidence isn't evidence.
- check_output: for every reply, redacts secrets, internal ids, internal
  tool names and personal contact details, and blocks system-prompt leaks
  and stack traces outright.

Lexical and rule-based on purpose: no second LLM call, no external service.
It errs toward leaving a claim out, never toward stating one it can't back.
"""
import os
import re
from typing import Iterable, List, Optional, Tuple

UNVERIFIED_COURTBAZAAR_MESSAGE = "I couldn't verify that from the available CourtBazaar information."
UNVERIFIED_GENERAL_MESSAGE = "I don't have enough verified information to answer that reliably."
PARTIAL_ANSWER_NOTE = "Some details couldn't be verified from the available information, so I've left them out."
LEGAL_VERIFY_NOTE = (
    "Please verify any specific section, time limit or figure with a qualified advocate or an official "
    "source before relying on it."
)
GENERAL_VERIFY_NOTE = "Any figures above are general information and weren't verified against a current source."
PROMPT_LEAK_MESSAGE = "I can't share details about how I'm set up. Is there anything else I can help you with?"
INTERNAL_ERROR_MESSAGE = "Sorry, something went wrong on my end. Please try again."
REDACTED = "[redacted]"

# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "ninety": "90",
    "hundred": "100",
}
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUMBER_WORD_RE = re.compile(r"\b(?:" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)
_LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:\d+[.)]|[•*-])\s+")
# Pricing/policy qualifiers — the words that turn a supported fact into an
# unsupported promise ("₹500" vs "₹500, including all court expenses").
_QUALIFIER_STEMS = (
    "includ", "inclusive", "exclud", "exclusive", "cover", "refundable", "non-refundable",
    "guarantee", "waive", "penalt", "additional", "extra", "gst", "tax", "discount",
    "mandatory", "compulsory", "free of", "free ",
)
_QUALIFIER_RE = re.compile(
    r"\b(?:includ\w*|inclusive|exclud\w*|exclusive|cover(?:s|ed|ing)?|refundable|non-refundable|"
    r"guarantee\w*|waive\w*|penalt\w*|additional|extra|gst|tax(?:es)?|discount\w*|mandatory|compulsory|"
    r"free)\b",
    re.IGNORECASE,
)
_COUNSEL_NAME_RE = re.compile(r"\bAdv(?:ocate)?\.?\s+[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*")
_CLAUSE_SEPARATOR_RE = re.compile(
    r",\s*|;\s*|\s+(?:and|but|which|plus|while|whereas|including)\s+", re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9₹\"'(])")
# A period after one of these doesn't end a sentence ("Adv. Mehta",
# "Kumar v. State", "Sec. 138", "Rs. 500").
_ABBREVIATION_END_RE = re.compile(
    r"\b(?:adv|mr|mrs|ms|dr|sr|jr|st|no|nos|sec|secs|art|arts|cl|ord|rs|vs|v|hon|ld|smt|shri|govt|dept|co|"
    r"ltd|pvt|inc|etc|e\.g|i\.e)\.$",
    re.IGNORECASE,
)


def _normalize_number(token: str) -> str:
    value = token.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value


def _numbers(text: str) -> set:
    found = {_normalize_number(t) for t in _NUMBER_RE.findall(text)}
    found |= {_NUMBER_WORDS[w.lower()] for w in _NUMBER_WORD_RE.findall(text)}
    return {n for n in found if n}


def _qualifier_supported(word: str, evidence_lower: str) -> bool:
    stem = word.lower()
    for known in _QUALIFIER_STEMS:
        if stem.startswith(known.strip()):
            return known.strip() in evidence_lower
    return stem in evidence_lower


_STOPWORDS = frozenset("""
a an the and or but if then than that this these those there their they them it its is are was were be been
being am do does did done have has had having can could may might must shall should will would not no nor
of in on at to for from by with about into over under between through during before after above below as
so such also only just very more most less much many any each every some all other own same both either
what which who whom whose when where why how i me my we our you your he him his she her us per via upon
according says said mentioned document documents sop diac rules rule courtbazaar court bazaar please
information details following provided include includes including available however therefore
""".split())
_WORD_RE = re.compile(r"[a-z][a-z'-]{2,}")


def _content_words(text: str) -> List[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def _content_supported(sentence: str, evidence_lower: str) -> bool:
    """For document evidence: at least half of a sentence's content words
    (matched on a 5-letter stem, so "processed"/"processing" agree) must
    occur in the retrieved text. Catches a fluent sentence that states a
    policy or requirement the document never mentions."""
    words = _content_words(_LIST_MARKER_RE.sub("", sentence))
    if len(words) < 2:
        return True
    hits = sum(1 for w in words if w[:5] in evidence_lower)
    return hits * 2 >= len(words)


def _clause_supported(clause: str, evidence_lower: str, evidence_numbers: set) -> bool:
    body = _LIST_MARKER_RE.sub("", clause)
    if not _numbers(body) <= evidence_numbers:
        return False
    for word in _QUALIFIER_RE.findall(body):
        if not _qualifier_supported(word, evidence_lower):
            return False
    for name in _COUNSEL_NAME_RE.findall(body):
        surname = re.sub(r"['’]s$", "", name.split()[-1]).lower()
        if surname not in evidence_lower:
            return False
    return True


# Text that follows or discusses injected instructions ("ignoring previous
# instructions", "the API key is ...") is never a supported claim, even when
# a malicious passage in the evidence contains the same words.
_INJECTION_ECHO_RE = re.compile(
    r"\bignor\w*\s+(?:all\s+|any\s+|the\s+|my\s+|your\s+)?(?:previous|prior|above|earlier|system|original)\b"
    r"|\bsystem prompt\b|\bdeveloper (?:prompt|message|instructions)\b|\bapi[ _-]?keys?\b|\bpasswords?\b"
    r"|\bsecret keys?\b|\baccess tokens?\b|\bnew instructions\b|\bjailbreak\b",
    re.IGNORECASE,
)


def _lines(text: str) -> List[Tuple[str, List[str]]]:
    """The answer as lines, each (list marker, [sentences]), so a filtered
    answer can be rebuilt with its original list/line structure."""
    lines = []
    for raw in (text or "").split("\n"):
        if not raw.strip():
            continue
        marker = _LIST_MARKER_RE.match(raw)
        prefix = marker.group(0) if marker else ""
        sentences: List[str] = []
        for piece in _SENTENCE_SPLIT_RE.split(raw[len(prefix):].strip()):
            if sentences and _ABBREVIATION_END_RE.search(sentences[-1]):
                sentences[-1] += " " + piece
            elif piece.strip():
                sentences.append(piece.strip())
        lines.append((prefix, sentences))
    return lines


def _rebuild(lines: List[Tuple[str, List[str]]]) -> str:
    return "\n".join(prefix + " ".join(sentences) for prefix, sentences in lines if sentences)


def _supported_prefix(sentence: str, evidence_lower: str, evidence_numbers: set) -> Optional[str]:
    """The longest leading run of supported clauses, or None if even the
    first clause is unsupported."""
    cuts = [0] + [m.start() for m in _CLAUSE_SEPARATOR_RE.finditer(sentence)] + [len(sentence)]
    starts = [0] + [m.end() for m in _CLAUSE_SEPARATOR_RE.finditer(sentence)]
    for i, start in enumerate(starts):
        clause = sentence[start:cuts[i + 1]]
        if not _clause_supported(clause, evidence_lower, evidence_numbers):
            if i == 0:
                return None
            kept = sentence[:cuts[i]].rstrip(" ,;:-")
            return kept if kept.endswith((".", "!", "?")) else kept + "."
    return sentence


# ---------------------------------------------------------------------------
# Grounded answers (RAG / live tool evidence)
# ---------------------------------------------------------------------------

def validate_grounded_answer(answer: str, evidence: str, document_evidence: bool = False) -> Optional[str]:
    """Keep only what the evidence supports. Returns the validated answer,
    or None when the unsupported part is large enough that what's left would
    be misleading — the caller then uses its safe fallback.

    `document_evidence` (RAG passages, i.e. natural-language evidence) also
    requires each sentence's wording to be substantially present in the
    evidence; structured live-tool evidence is checked on its facts only."""
    if not answer or not answer.strip():
        return None
    evidence_lower = (evidence or "").lower()
    evidence_numbers = _numbers(evidence or "")
    lines = []
    kept_count = dropped = truncated = 0
    for marker, sentences in _lines(answer):
        kept: List[str] = []
        for sentence in sentences:
            if _INJECTION_ECHO_RE.search(sentence) or (
                    document_evidence and not _content_supported(sentence, evidence_lower)):
                dropped += 1
                continue
            supported = _supported_prefix(sentence, evidence_lower, evidence_numbers)
            if supported is None:
                dropped += 1
                continue
            if supported != sentence:
                truncated += 1
            kept.append(supported)
        kept_count += len(kept)
        lines.append((marker, kept))
    if not kept_count or dropped > kept_count:
        return None
    result = _rebuild(lines)
    if dropped or truncated:
        result += "\n\n" + PARTIAL_ANSWER_NOTE
    return result


# ---------------------------------------------------------------------------
# General-knowledge answers (no retrieved evidence)
# ---------------------------------------------------------------------------

_COURTBAZAAR_TERM_RE = re.compile(
    r"\b(?:court\s*bazaar|courtbazaar|proxy[- ]counsels?|our platform|this platform|the platform)\b", re.IGNORECASE,
)
_COURTBAZAAR_FACT_RE = re.compile(
    r"\d|₹|\brs\.?\b|\b(?:refund\w*|fees?|pric\w*|charges?|costs?|polic\w*|availab\w*|guarantee\w*|within|"
    r"deadline|sla|turnaround|commission|discount\w*|cancel\w*)\b",
    re.IGNORECASE,
)
_CASE_CITATION_RE = re.compile(
    r"\b[A-Z][\w.&'-]*(?:\s+(?:of\s+)?[A-Z][\w.&'-]*)*\s+(?:v\.|vs\.?|versus)\s+[A-Z]"
    r"|\bAIR\s+\d{4}\b|\(\d{4}\)\s*\d+\s+SCC\b|\b\d{4}\s+SCC\b|\bSCC\s+OnLine\b|\bSCR\s+\d+",
)
_LONG_QUOTE_RE = re.compile(r"[\"“]([^\"”]{40,})[\"”]")
_LEGAL_FIGURE_RE = re.compile(
    r"\b(?:section|sec\.|article|art\.|order|rule|regulation|schedule)\s+\d+"
    r"|\b\d+\s*(?:days?|weeks?|months?|years?)\b|\d+(?:\.\d+)?\s*%|₹\s*\d|\brs\.?\s*\d",
    re.IGNORECASE,
)
_STATISTIC_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:million|billion|crore|lakh)\b", re.IGNORECASE)


def guard_general_answer(answer: str, legal: bool) -> str:
    """No retrieved evidence backs this answer, so: drop CourtBazaar-specific
    claims, unverifiable case citations, and long quotations; qualify legal
    figures (sections, time limits, amounts) and statistics as unverified."""
    lines = []
    kept_count = dropped_courtbazaar = dropped_other = 0
    for marker, sentences in _lines(answer):
        kept: List[str] = []
        for sentence in sentences:
            if _COURTBAZAAR_TERM_RE.search(sentence) and _COURTBAZAAR_FACT_RE.search(sentence):
                dropped_courtbazaar += 1
                continue
            if _CASE_CITATION_RE.search(sentence) or _LONG_QUOTE_RE.search(sentence):
                dropped_other += 1
                continue
            kept.append(sentence)
        kept_count += len(kept)
        lines.append((marker, kept))
    if not kept_count:
        return UNVERIFIED_COURTBAZAAR_MESSAGE if dropped_courtbazaar else UNVERIFIED_GENERAL_MESSAGE
    result = _rebuild(lines)
    notes = []
    if dropped_courtbazaar:
        notes.append(UNVERIFIED_COURTBAZAAR_MESSAGE)
    if legal and _LEGAL_FIGURE_RE.search(result):
        notes.append(LEGAL_VERIFY_NOTE)
    elif not legal and _STATISTIC_RE.search(result):
        notes.append(GENERAL_VERIFY_NOTE)
    if dropped_other and not notes:
        notes.append(PARTIAL_ANSWER_NOTE)
    return result + ("\n\n" + " ".join(notes) if notes else "")


# ---------------------------------------------------------------------------
# Output safety (every reply)
# ---------------------------------------------------------------------------

_SECRET_RES = [re.compile(p) for p in (
    r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{16,}",
    r"\bgsk_[A-Za-z0-9]{16,}",
    r"\brzp_(?:live|test)_[A-Za-z0-9]{8,}",
    r"\bAIza[0-9A-Za-z_-]{30,}",
    r"\bxkeysib-[A-Za-z0-9-]{16,}",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"(?i)\bbearer\s+[A-Za-z0-9._-]{16,}",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    r"mongodb(?:\+srv)?://\S+",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
    r"(?i)\b(?:api[_-]?key|secret(?:[_-]?key)?|password|passwd|access[_-]?token)\s*[:=]\s*\S{6,}",
)]
# Internal record ids: prefix_<hex> (user_, adv_, hearing_, conv_, pay_, ...),
# order ids (ORD + yymmdd + 6 hex), and Mongo ObjectIds.
_INTERNAL_ID_RE = re.compile(r"\b(?:[a-z]{2,8}_[0-9a-f]{6,16}|ORD\d{6}[0-9A-F]{6}|[0-9a-f]{24})\b")
_INTERNAL_NAME_RE = re.compile(
    r"\b(?:search_proxy_counsels|get_proxy_counsel_profile|get_states|get_courts|get_court|get_services|"
    r"get_my_orders|get_order|get_my_hearing_requests|get_hearing_request|filters_applied|total_candidates|"
    r"court_bazaar_tools|llm_service|ai_chat|answer_guard|vector_stores?|file_search|untrusted_tool_data|"
    r"untrusted_document_excerpts)\b",
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PUBLIC_EMAIL_DOMAIN_RE = re.compile(r"@(?:[\w-]+\.)*courtbazaar\.[a-z.]+$", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<![\d+])(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")
_STACK_TRACE_RE = re.compile(r"Traceback \(most recent call last\)|File \"[^\"]+\.py\", line \d+")
# A reply announcing that it is following injected instructions.
_INJECTION_COMPLIANCE_RE = re.compile(
    r"\b(?:ignoring|disregarding|overriding)\s+(?:all\s+|any\s+|the\s+|my\s+)?(?:previous|prior|above|earlier|"
    r"system|original)\s+(?:instructions|rules|prompts?)\b"
    r"|\bmy (?:system prompt|instructions) (?:is|are|says?)\b|\bhere (?:is|are) my (?:system prompt|instructions)\b",
    re.IGNORECASE,
)
_SECRET_ENV_HINT_RE = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASS\b|MONGO_URL", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _configured_secret_values() -> List[str]:
    return [v for k, v in os.environ.items() if _SECRET_ENV_HINT_RE.search(k) and v and len(v) >= 8]


_INSTRUCTION_WORD_RE = re.compile(
    r"\b(?:you|your|never|do not|don't|must|should|rules?|instructions?|answer|reply|ignore)\b", re.IGNORECASE,
)


def _protected_fragments(protected_texts: Iterable[str]) -> List[str]:
    """Instruction sentences of the hidden prompts that are long enough to
    be distinctive. Plain factual sentences in a prompt (e.g. which statutes
    replaced which) aren't secret — a correct answer may repeat them."""
    fragments = []
    for text in protected_texts:
        for piece in re.split(r"(?<=[.!?:])\s+|\n+", text or ""):
            norm = _WHITESPACE_RE.sub(" ", piece).strip().lower()
            if len(norm) >= 50 and _INSTRUCTION_WORD_RE.search(norm):
                fragments.append(norm)
    return fragments


def check_output(text: str, protected_texts: Iterable[str] = ()) -> Tuple[str, List[str]]:
    """Final safety pass over a reply. Returns (safe_text, flags). A prompt
    leak or stack trace replaces the whole reply; secrets, internal ids,
    internal names, emails and phone numbers are redacted in place. The
    flags are for server logs — the user never sees why."""
    if not text:
        return text, []
    flags: List[str] = []
    normalized = _WHITESPACE_RE.sub(" ", text).lower()
    if any(fragment in normalized for fragment in _protected_fragments(protected_texts)):
        return PROMPT_LEAK_MESSAGE, ["prompt_leak"]
    if _STACK_TRACE_RE.search(text):
        return INTERNAL_ERROR_MESSAGE, ["stack_trace"]
    if _INJECTION_COMPLIANCE_RE.search(text):
        return PROMPT_LEAK_MESSAGE, ["injection_compliance"]

    cleaned = text
    for value in _configured_secret_values():
        if value in cleaned:
            cleaned = cleaned.replace(value, REDACTED)
            flags.append("configured_secret")
    for pattern in _SECRET_RES:
        cleaned, n = pattern.subn(REDACTED, cleaned)
        if n:
            flags.append("secret_pattern")
    for name, pattern in (("internal_id", _INTERNAL_ID_RE), ("phone", _PHONE_RE)):
        cleaned, n = pattern.subn(REDACTED, cleaned)
        if n:
            flags.append(name)
    # CourtBazaar's own public addresses (e.g. a support mailbox in the SOP)
    # are fine; any other email address is treated as personal data.
    personal_emails = [e for e in _EMAIL_RE.findall(cleaned) if not _PUBLIC_EMAIL_DOMAIN_RE.search(e)]
    if personal_emails:
        cleaned = _EMAIL_RE.sub(
            lambda m: m.group(0) if _PUBLIC_EMAIL_DOMAIN_RE.search(m.group(0)) else REDACTED, cleaned,
        )
        flags.append("email")
    cleaned, n = _INTERNAL_NAME_RE.subn("", cleaned)
    if n:
        flags.append("internal_name")
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(), flags
