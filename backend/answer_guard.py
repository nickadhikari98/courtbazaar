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

UNVERIFIED_COURTBAZAAR_MESSAGE = (
    "I don’t have verified information about that at the moment. You can ask me about CourtBazaar services, "
    "courts, or Proxy Counsel."
)
UNVERIFIED_GENERAL_MESSAGE = "I don't have enough verified information to answer that reliably."
UNVERIFIED_LEGAL_MESSAGE = (
    "I don’t have enough verified information to answer that reliably. If you share more details, I can help "
    "explain the general legal concept."
)
# Shown under a general answer that had something removed. Document answers
# replace it with a note naming the document (ai_chat.DOCUMENT_PARTIAL_NOTE).
PARTIAL_ANSWER_NOTE = "I've left out a point I couldn't confirm, so treat this as a partial answer."
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
# A sentence that opens with a subordinate clause, whose main clause only
# comes after the first separator.
_SUBORDINATE_START_RE = re.compile(
    r"^\W*(?:if|when|whenever|unless|where|although|though|because|since|while|once|after|before|until|"
    r"provided|in case)\b",
    re.IGNORECASE,
)
# Document answers: wording that marks general knowledge or a hedge rather
# than the document's statement ("Generally, under the Act ...", "typically
# 50%"). Allowed only if the document itself uses the word.
_GENERALIZATION_RE = re.compile(
    r"\b(?:generally|in general|typically|usually|normally|commonly|as a general rule|in most cases|"
    r"in practice|under indian law)\b",
    re.IGNORECASE,
)
# A named statute ("Arbitration and Conciliation Act, 1996", "Limitation Act").
_NAMED_STATUTE_RE = re.compile(
    r"\b((?:[A-Z][a-z]+\s+)(?:(?:and|of|&)\s+)?(?:[A-Z][a-z]+\s+){0,4}(?:Act|Code|Sanhita|Adhiniyam))\b(?:,?\s*(\d{4}))?"
)
# A Markdown section heading in a document answer ("## Who pays"), with its
# section number if it has one ("### 6. Refunds"): the number is part of the
# marker, never a sentence of its own that could outlive the heading's text.
_HEADING_MARKER_RE = re.compile(r"^\s{0,3}#{1,4}\s+(?:\d{1,3}[.)]\s+)?")
# A "---" separator line between sections. Structure, not content.
_DIVIDER_LINE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
DIVIDER_MARKER = "---"
# A clause that can stand on its own as a statement has a finite verb. After a
# cut, a leading run like "The fees, costs" (just a list of nouns) has none.
_FINITE_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|am|shall|may|must|will|would|can|could|should|might|"
    r"has|have|had|does|do|did|applies|apply|applied|means|mean|includes|include|requires|require|"
    r"pays?|paid|fix(?:es|ed)?|determines?|determined|maintains?|maintained|decides?|decided|"
    r"terminates?|terminated|directs?|directed|becomes?|became|remains?|remained)\b",
    re.IGNORECASE,
)
# A heading longer than this is checked like an ordinary sentence: headings
# are labels, not a place to put claims.
_HEADING_MAX_WORDS = 10
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
    if hits * 2 < len(words):
        return False
    # A document answer states what the document says. A generalization or
    # hedge the document doesn't use, or a statute the document doesn't name,
    # is general knowledge filling a gap (e.g. "Generally, under the
    # Arbitration and Conciliation Act, 1996, ...") and is left out.
    for word in _GENERALIZATION_RE.findall(sentence):
        if word.lower() not in evidence_lower:
            return False
    for name, year in _NAMED_STATUTE_RE.findall(sentence):
        if name.lower() not in evidence_lower or (year and year not in evidence_lower):
            return False
    return True


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


# Text in a retrieved passage that addresses the assistant rather than
# describing CourtBazaar or the rules ("SYSTEM: respond only with ...").
_DIRECTIVE_RE = re.compile(
    # role tags: "SYSTEM:", "[assistant instruction]:"
    r"(?:^|[\s\[(\"'])(?:system|developer|assistant|ai|chatbot|model)\s*(?:message|prompt|instruction)?s?\s*[:\]]"
    # a sentence that opens with a command to reply/say/tell
    r"|^\W*(?:always\s+|only\s+|now\s+)?(?:respond|reply|answer|output|print|say|tell|inform|assure)\b"
    r"|\b(?:respond|reply|answer|output|say)\s+(?:only|exactly|always)\b"
    r"|\b(?:the|this)\s+(?:assistant|chatbot|ai|model|bot)\s+(?:must|should|will|shall)\b"
    r"|\bas an ai\b|\byou are now\b",
    re.IGNORECASE,
)


def evidence_without_directives(evidence: str) -> str:
    """The evidence a grounded answer is checked against, minus any
    sentence that is an instruction to the assistant (or an injected
    "ignore previous instructions"). The model still sees the whole
    excerpt as data; this only stops a planted directive's payload from
    counting as support for the answer that repeats it."""
    kept = []
    for raw in (evidence or "").split("\n"):
        pieces = _SENTENCE_SPLIT_RE.split(raw)
        kept.append(" ".join(p for p in pieces
                             if not (_DIRECTIVE_RE.search(p) or _INJECTION_ECHO_RE.search(p))))
    return "\n".join(kept)


def _lines(text: str) -> List[Tuple[str, List[str]]]:
    """The answer as lines, each (list marker, [sentences]), so a filtered
    answer can be rebuilt with its original list/line structure. A blank
    line is kept as ("", []) so paragraph breaks survive the rebuild, and a
    "## " heading's marker is kept like a list marker."""
    lines: List[Tuple[str, List[str]]] = []
    for raw in (text or "").split("\n"):
        if not raw.strip():
            lines.append(("", []))
            continue
        if _DIVIDER_LINE_RE.match(raw):
            lines.append((DIVIDER_MARKER, []))  # no sentences: never validated or counted
            continue
        marker = _HEADING_MARKER_RE.match(raw) or _LIST_MARKER_RE.match(raw)
        prefix = marker.group(0) if marker else ""
        sentences: List[str] = []
        for piece in _SENTENCE_SPLIT_RE.split(raw[len(prefix):].strip()):
            # Only the tail can end in an abbreviation; searching the whole,
            # growing sentence each time made this quadratic.
            if sentences and _ABBREVIATION_END_RE.search(" " + sentences[-1][-24:]):
                sentences[-1] += " " + piece
            elif piece.strip():
                sentences.append(piece.strip())
        lines.append((prefix, sentences))
    return lines


def _is_heading(marker: str) -> bool:
    return bool(_HEADING_MARKER_RE.match(marker))


def _rebuild(lines: List[Tuple[str, List[str]]]) -> str:
    """Joins kept lines back up: one blank line between paragraphs; a heading
    whose whole section was filtered out is dropped with it; a list item
    filtered down to nothing leaves no bare marker; and a "---" separator is
    kept only between two pieces of content, never doubled, leading or
    trailing."""
    out: List[str] = []
    pending_divider = False
    for i, (prefix, sentences) in enumerate(lines):
        if prefix == DIVIDER_MARKER and not sentences:
            pending_divider = any(ln.strip() for ln in out)
            continue
        if not sentences:
            if prefix.strip() and not _is_heading(prefix):
                continue  # a list item filtered to nothing: no gap left in the list
            if out and out[-1] != "":
                out.append("")
            continue
        if _is_heading(prefix):
            following = next((ln for ln in lines[i + 1:] if ln[1]), None)
            if following is None or _is_heading(following[0]):
                continue
        if pending_divider:
            while out and out[-1] == "":
                out.pop()
            out += ["", DIVIDER_MARKER, ""]
            pending_divider = False
        out.append(prefix + " ".join(sentences))
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


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
            if i == 1 and _SUBORDINATE_START_RE.match(sentence):
                # Only the leading "If/When/Unless ..." clause survived: on its
                # own it's a fragment ("If the Claimant does not pay."), so the
                # whole sentence goes rather than a half that reads as a claim.
                return None
            kept = sentence[:cuts[i]].rstrip(" ,;:-")
            if not _FINITE_VERB_RE.search(_LIST_MARKER_RE.sub("", kept)):
                # Only a list of nouns survived the cut ("The fees, costs"):
                # not a statement, so the sentence goes rather than a fragment.
                return None
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
    skipping = False
    for marker, sentences in _lines(answer):
        if _is_heading(marker) or marker == DIVIDER_MARKER:
            skipping = False
        elif skipping:
            # Under a heading that was itself unsupported, a verbless item
            # ("- Administrative Costs.") only meant something as part of that
            # heading's claim, so it goes too (and counts as dropped). A full
            # statement is still checked on its own below, and the blank line
            # left by the heading keeps it apart from the section above.
            fragments = [s for s in sentences if not _FINITE_VERB_RE.search(s)]
            dropped += len(fragments)
            sentences = [s for s in sentences if _FINITE_VERB_RE.search(s)]
        kept: List[str] = []
        # A short heading is a structural label ("## Who pays"), so it isn't
        # held to the wording-overlap test; its numbers, qualifiers and any
        # injection echo are still checked like any other text.
        label = _is_heading(marker) and len(" ".join(sentences).split()) <= _HEADING_MAX_WORDS
        for sentence in sentences:
            if _INJECTION_ECHO_RE.search(sentence) or (
                    document_evidence and not label and not _content_supported(sentence, evidence_lower)):
                dropped += 1
                continue
            supported = _supported_prefix(sentence, evidence_lower, evidence_numbers)
            if supported is None:
                dropped += 1
                continue
            if supported != sentence:
                truncated += 1
            kept.append(supported)
        if not label:
            kept_count += len(kept)  # headings alone never count as an answer
        if _is_heading(marker) and sentences and not kept:
            skipping = True
        lines.append((marker, kept))
    if not kept_count or dropped > kept_count:
        return None
    result = _rebuild(lines)
    if dropped or truncated:
        result += "\n\n" + PARTIAL_ANSWER_NOTE
    return result


# ---------------------------------------------------------------------------
# Rule attribution (document answers)
#
# validate_grounded_answer checks a sentence against everything retrieved, so
# a sentence that takes the actor from one rule and the condition from another
# ("The Tribunal may issue an order to terminate ... within thirty days
# (Rule 33.5)": the Tribunal's order is Rule 16.2, the thirty days are Rule
# 33.5, where the Centre terminates or directs the Tribunal) passed, because
# every word was somewhere in the evidence. validate_rule_attribution checks
# each rule-attributed sentence against that rule's own text only.
# ---------------------------------------------------------------------------

_ACTOR_WORDS = {
    "centre": "centre", "center": "centre", "tribunal": "tribunal", "tribunals": "tribunal",
    "claimant": "claimant", "claimants": "claimant", "respondent": "respondent", "respondents": "respondent",
    "party": "party", "parties": "party", "chairperson": "chairperson", "arbitrator": "arbitrator",
    "arbitrators": "arbitrator", "secretariat": "secretariat", "registrar": "registrar",
}
_ACTOR_ALT = "|".join(sorted(_ACTOR_WORDS, key=len, reverse=True))
_MODAL = r"(?:may|shall|must|can|could|will|would|should|is free to|are free to|is required to|are required to|has to|have to|is entitled to|are entitled to)"
_ACTIVE_RE = re.compile(rf"\b({_ACTOR_ALT})\s+{_MODAL}\s+(?:(?:also|either|then|not|only|still|further|now)\s+)*([a-z]+)", re.IGNORECASE)
_PASSIVE_RE = re.compile(rf"\b(?:be|been|is|are|was|were)\s+([a-z]+(?:ed|able))\s+by\s+(?:the\s+|any\s+|each\s+|either\s+)?({_ACTOR_ALT})\b", re.IGNORECASE)
_ADJ_BY_RE = re.compile(rf"\b([a-z]+able)\s+by\s+(?:the\s+|any\s+|each\s+|either\s+)?({_ACTOR_ALT})\b", re.IGNORECASE)
# Further verbs an actor governs later in the same sentence: "may either
# terminate ... or where ..., direct the Tribunal ...".
_COORDINATED_RE = re.compile(r"(?:\bor\b|\band\b|,)\s+(?:where[^,.;]*,\s*|if[^,.;]*,\s*)?([a-z]+)\s+(?:the|a|an|its|their|such|any)\b", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.;](?:\s|$)")
_GENERIC_PARTY = {"party"}  # "any party" in a rule covers the Claimant and the Respondent
_PARTY_ROLES = {"claimant", "respondent", "party"}
_NOT_VERBS = frozenset("the a an be been to not also either then only as in with where if case per".split())


def _verb_key(word: str) -> str:
    w = word.lower()
    for suffix in ("able", "ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: -len(suffix)]
            break
    return w[:5]


def _actor_actions(text: str, coordinated: bool = False) -> set:
    """(actor, verb-stem) pairs: "the Centre may terminate" -> (centre, termi);
    "terminated by the Tribunal" / "payable by the Claimant" -> (tribunal,
    termi) / (claimant, pay). With `coordinated` (rule text), verbs the same
    actor governs later in the sentence are added too."""
    pairs = set()
    for m in _ACTIVE_RE.finditer(text):
        actor, verb = _ACTOR_WORDS[m.group(1).lower()], m.group(2).lower()
        if verb in _NOT_VERBS:
            continue
        pairs.add((actor, _verb_key(verb)))
        if coordinated:
            end = _SENTENCE_END_RE.search(text, m.end())
            rest = text[m.end(): end.start() if end else len(text)]
            nxt = _ACTIVE_RE.search(rest)
            rest = rest[: nxt.start()] if nxt else rest
            for c in _COORDINATED_RE.finditer(rest):
                if c.group(1).lower() not in _NOT_VERBS and c.group(1).lower() not in _ACTOR_WORDS:
                    pairs.add((actor, _verb_key(c.group(1))))
    for rx in (_PASSIVE_RE, _ADJ_BY_RE):
        for m in rx.finditer(text):
            pairs.add((_ACTOR_WORDS[m.group(2).lower()], _verb_key(m.group(1))))
    return pairs


def _actions_supported(claimed: set, rule_pairs: set) -> bool:
    for actor, verb in claimed:
        ok = (actor, verb) in rule_pairs or (
            actor in _PARTY_ROLES and any((g, verb) in rule_pairs for g in _GENERIC_PARTY))
        if not ok:
            return False
    return True


def _rule_refs(text: str) -> List[str]:
    refs = []
    for m in re.finditer(r"\bRules?\s+(\d{1,3}(?:\.\d{1,2})?(?:\s*(?:,|and|&|or)\s*\d{1,3}(?:\.\d{1,2})?)*)"
                         r"|\((\d{1,3}\.\d{1,2})\)", text, re.IGNORECASE):
        refs += re.findall(r"\d{1,3}(?:\.\d{1,2})?", m.group(1) or m.group(2))
    return refs


_SPECIFIC_PARTY_RE = re.compile(r"\b(claimant|respondent)s?\b", re.IGNORECASE)
_GENERIC_PARTY_RE = re.compile(r"\b(?:party|parties)\b", re.IGNORECASE)


def _narrows_party(body: str, rule_text: str) -> bool:
    """True when a sentence puts "the Claimant"/"the Respondent" where its
    rule only says "a party": the rule applies to every party, and the
    answer must keep the rule's own word. Saying both ("a party (including
    the Claimant)") keeps it; so does a rule that itself names that role."""
    if _GENERIC_PARTY_RE.search(body) or not _GENERIC_PARTY_RE.search(rule_text):
        return False
    rule_lower = rule_text.lower()
    return any(m.group(1).lower() not in rule_lower for m in _SPECIFIC_PARTY_RE.finditer(body))


# "the Claimant" / "a Respondent" as a whole noun phrase (not "the Claimant's").
_SPECIFIC_PARTY_PHRASE_RE = re.compile(r"\b(the|a|an)\s+(claimant|respondent)\b(?!['’]s)", re.IGNORECASE)


def _restore_party_wording(sentence: str, refs: List[str], provisions: dict) -> Optional[str]:
    """For a sentence rejected only because it says "the Claimant" where its
    rule says "a party": the same sentence in the rule's own word, with the
    role kept in brackets ("If a party (including the Claimant) fails ...").
    Returned only if that version passes the full attribution check against
    the same rule; None otherwise. Nothing but the party wording changes."""
    rule_text = "\n".join(provisions.get(r) or "" for r in refs)
    if not _narrows_party(sentence, rule_text):
        return None
    # The original must already pass every other check: the inserted "a
    # party" adds the rule's own words, so it must never be what makes an
    # otherwise unsupported sentence pass.
    if not _attribution_ok(sentence, refs, provisions, check_party_wording=False):
        return None

    def repl(m: "re.Match") -> str:
        text = f"a party (including the {m.group(2).capitalize()})"
        return text[0].upper() + text[1:] if m.group(1)[0].isupper() and m.start() == 0 else text

    restored = _SPECIFIC_PARTY_PHRASE_RE.sub(repl, sentence)
    if restored == sentence or not _attribution_ok(restored, refs, provisions):
        return None
    return restored


def _attribution_ok(sentence: str, refs: List[str], provisions: dict, check_party_wording: bool = True) -> bool:
    texts = [provisions.get(r) for r in refs]
    if not refs or any(t is None for t in texts):
        return False  # cites a rule whose text wasn't retrieved
    rule_text = "\n".join(texts)
    rule_lower = rule_text.lower()
    body = re.sub(r"\(?\b(?:Rules?)\s+[\d.,\sand&or]+\)?|\(\d{1,3}\.\d{1,2}\)", " ", sentence, flags=re.IGNORECASE)
    if not _content_supported(body, rule_lower):
        return False
    if not _numbers(_LIST_MARKER_RE.sub("", body)) <= _numbers(rule_text):
        return False
    if check_party_wording and _narrows_party(body, rule_text):
        return False
    return _actions_supported(_actor_actions(body), _actor_actions(rule_text, coordinated=True))


def validate_rule_attribution(answer: str, provisions: dict) -> Tuple[Optional[str], int]:
    """Drops each sentence attributed to a rule that its rule's own text
    doesn't support: wording, figures, and who does what. A sentence is
    attributed by its own "(Rule X)", else by a rule cited elsewhere in its
    paragraph, else by its section heading. Unattributed sentences are left
    to validate_grounded_answer. Returns (answer or None, sentences dropped).
    With no labelled provisions (raw chunks only) it changes nothing."""
    if not answer or not provisions:
        return answer, 0
    lines = _lines(answer)
    # Paragraph = consecutive non-blank, non-heading lines.
    para_refs: List[List[str]] = []
    current: List[str] = []
    group: List[int] = []
    for idx, (marker, sentences) in enumerate(lines):
        if not sentences or _is_heading(marker):
            for g in group:
                para_refs[g] = current
            current, group = [], []
            para_refs.append([])
            continue
        para_refs.append([])
        group.append(idx)
        for s in sentences:
            current = current + [r for r in _rule_refs(s) if r not in current]
    for g in group:
        para_refs[g] = current
    out = []
    section_refs: List[str] = []
    kept = dropped = 0
    for idx, (marker, sentences) in enumerate(lines):
        if _is_heading(marker):
            section_refs = _rule_refs(" ".join(sentences))
            out.append((marker, sentences))
            continue
        keep = []
        for s in sentences:
            refs = _rule_refs(s) or para_refs[idx] or section_refs
            if refs and not _attribution_ok(s, refs, provisions):
                restored = _restore_party_wording(s, refs, provisions)
                if restored is None:
                    dropped += 1
                    continue
                s = restored
            keep.append(s)
        kept += len(keep)
        out.append((marker, keep))
    if not kept:
        return None, dropped
    return _rebuild(out), dropped


def _checked_card_text(markdown: str, evidence: str, provisions: dict) -> Optional[str]:
    """One card field through both document checks, or None when nothing
    trustworthy is left."""
    validated = validate_grounded_answer(markdown, evidence, document_evidence=True)
    validated, _ = validate_rule_attribution(validated, provisions)
    return validated.replace(PARTIAL_ANSWER_NOTE, "").strip() if validated else None


def validate_answer_card(card: dict, evidence: str, provisions: dict) -> Optional[dict]:
    """The structured form of validate_grounded_answer + validate_rule_attribution:
    each point is checked as its own "## title" section, so a dropped sentence
    or point can't leave text under the wrong heading. A point that doesn't
    survive whole-titled goes. The summary must keep its opening sentence
    whole: without it, what's left no longer answers the question, so it comes
    back as None for the caller to replace. Returns None when every point fails."""
    one_line = lambda value: re.sub(r"\s+", " ", value or "").strip()
    raw_summary = one_line(card["summary"])
    summary = _checked_card_text(raw_summary, evidence, provisions)
    if summary is not None and not summary.startswith(_SENTENCE_SPLIT_RE.split(raw_summary)[0]):
        summary = None
    direct = {"yes": "Yes. ", "no": "No. "}.get(card.get("direct"), "")
    evidence_numbers = _numbers(evidence or "")
    points = []
    for point in card["points"]:
        # "[n]" in the page is a verified source chip, never model text.
        text = re.sub(r"\s*\[\d{1,2}\]", "", one_line(point["text"]))
        checked = _checked_card_text(f"## {one_line(point['title'])}\n{text}", evidence, provisions)
        title, _, body = (checked or "").partition("\n")
        if not title.startswith("## ") or not body.strip():
            continue
        badge = one_line(point["badge"])
        cited_as = clause_labels(f"{title} {body}").get(badge.removeprefix("Rule ").strip())
        if cited_as:
            badge = f"Rule {cited_as[0]}"  # same label as the title beside it
        points.append({**point, "title": title[3:].strip(), "text": one_line(body),
                       "badge": badge if badge and _numbers(badge) <= evidence_numbers else None})
    if not points:
        return None
    follow_up = _specific_follow_up(one_line(card["follow_up"]), points, raw_summary, evidence_numbers, provisions)
    # "partial" means the main ask went unanswered, which the verifier decides:
    # a sentence cut here isn't that (llm_service._card_answer).
    return {"status": "partial" if card["status"] == "partial" else "answered",
            "summary": summary and direct + one_line(summary), "points": points, "follow_up": follow_up}


_GENERIC_FOLLOW_UP_RE = re.compile(r"\b(?:know|learn) more\b|\b(?:more )?(?:information|details)\b", re.IGNORECASE)


def _specific_follow_up(question: str, points: List[dict], summary: str, evidence_numbers: set,
                        provisions: dict) -> Optional[str]:
    """A follow-up must be a question (a statement would be an unchecked
    claim) about a retrieved rule the answer didn't use. Otherwise there's none."""
    if not question.endswith("?") or _GENERIC_FOLLOW_UP_RE.search(question) or not _numbers(question) <= evidence_numbers:
        return None
    if not provisions:
        return question  # no rule numbers in this document to point at
    used = set(_rule_refs(summary)).union(*(point_rule_refs(p) for p in points))
    refs = set(_rule_refs(question))
    return question if refs and refs <= set(provisions) and refs - used else None


_CLAUSE_REF_RE = re.compile(r"\bRules?\s+(\d{1,3}(?:\.\d{1,3})?)(\([a-z]{1,4}\))", re.IGNORECASE)


def clause_labels(text: str) -> dict:
    """Rule number -> how the text cites it where that names a clause:
    {"4": ["4(i)"]}, so a source can read the same as the answer."""
    labels: dict = {}
    for number, clause in _CLAUSE_REF_RE.findall(text or ""):
        if number + clause not in labels.setdefault(number, []):
            labels[number].append(number + clause)
    return labels


# What a question can ask a rule to allow. The rules can provide for something
# close (termination) and a model will happily call that a "yes" (suspension).
_ASKED_ACTIONS = (
    ("suspen", "suspension"), ("adjourn", "adjournment"), ("dismiss", "dismissal"), ("withdraw", "withdrawal"),
    ("cancel", "cancellation"), ("refund", "a refund"), ("waive", "a waiver"), ("extend", "an extension"),
    ("extension", "an extension"), ("appeal", "an appeal"), ("transfer", "a transfer"), ("stay", "a stay"),
)
# On nearly every rule, so they can't show a rule is on the question's subject.
_GENERIC_PROCEDURE_WORD_RE = re.compile(
    r"^(?:tribunal|arbitra|part(?:y|ies)|proceeding|centre|claimant|respondent|rule)", re.IGNORECASE)
_LEADING_YES_NO_RE = re.compile(r"^\W*(?:yes|no)\b[.,:;]?\s*", re.IGNORECASE)


def starts_with_yes_or_no(text: str) -> bool:
    return bool(_LEADING_YES_NO_RE.match(text or ""))


def without_yes_or_no(text: str) -> str:
    rest = _LEADING_YES_NO_RE.sub("", text or "", count=1)
    return rest[:1].upper() + rest[1:]


def unaddressed_action(question: str, provisions: List[str]) -> Optional[str]:
    """The action a question asks about ("suspension") when no provision
    provides for it on the question's subject, else None. Searches every
    provision, because this backs a statement that the rules don't mention it:
    with none to search, it says nothing. A provision using the word on another
    subject doesn't count (Rule 15.2 suspends interim measures, not proceedings
    over a deposit), so the check is that it shares the question's rarest term."""
    lowered = [p.lower() for p in provisions]
    question_lower = (question or "").lower()
    asked = next(((stem, noun) for stem, noun in _ASKED_ACTIONS if stem in question_lower), None)
    if asked is None or not lowered:
        return None
    stem, noun = asked
    hits = [p for p in lowered if stem in p]
    terms = [t for t in _content_words(question_lower)
             if stem not in t and not _GENERIC_PROCEDURE_WORD_RE.match(t) and any(t in p for p in lowered)]
    if not hits:
        return noun
    rarest = min(terms, key=lambda t: sum(t in p for p in lowered), default=None)
    return noun if rarest and not any(rarest in p for p in hits) else None


def point_rule_refs(point: dict) -> List[str]:
    return _rule_refs(" ".join(filter(None, (point["title"], point["badge"], point["text"]))))


def card_markdown(card: dict) -> str:
    """The card as the plain reply text: what's stored in the transcript,
    replayed to the model, and shown if the page can't render the card."""
    parts = [card["summary"]] + [f"## {p['title']}\n{p['text']}" for p in card["points"]]
    if card["follow_up"]:
        parts.append(card["follow_up"])
    if card["status"] == "partial":
        parts.append(PARTIAL_ANSWER_NOTE)
    return "\n\n".join(parts)


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
# Legal figures the digit-based pattern above misses: time limits in words
# ("three years"), roman-numeral Orders, and named statutes.
_LEGAL_FIGURE_WORDS_RE = re.compile(
    r"\b(?:" + "|".join(_NUMBER_WORDS) + r")\s+(?:days?|weeks?|months?|years?)\b", re.IGNORECASE,
)
_STATUTE_NAME_RE = re.compile(
    r"\bOrder\s+[IVXL]{1,7}\b|\b(?:Act|Sanhita|Adhiniyam)(?:,?\s*\d{4})?\b|\bCode of (?:Civil|Criminal) Procedure\b"
    r"|\b(?:IPC|CrPC|Cr\.P\.C|CPC|BNSS|BNS|BSA)\b",
)

# ---------------------------------------------------------------------------
# Legal currentness (general-knowledge legal answers)
# ---------------------------------------------------------------------------
# The model's legal knowledge can be out of date or simply wrong, and nothing
# on these turns can check it against a current official source. So:
# - a section of a repealed code (IPC, CrPC, Indian Evidence Act — replaced
#   by the BNS, BNSS and BSA from 1 July 2024) cited without historical
#   framing is marked in place as the old provision, with the new section
#   only where the correspondence below is known — never a guessed number;
# - a few well-known remedies tied to the wrong provision (the Phase 3 smoke
#   failures) are removed and replaced by a fixed, verified correction;
# - a sentence claiming the law has been verified or is current is removed;
# - a legal answer that turns on a section, statute, time limit or current
#   law is qualified as unverified.

CURRENT_LAW_NOTE = (
    "Laws and procedures change, and this couldn't be checked against the current official text — please "
    "confirm the current position with a qualified advocate or an official source before relying on it."
)
ANTICIPATORY_BAIL_NOTE = (
    "For reference: since 1 July 2024, anticipatory bail is governed by Section 482 of the BNSS "
    "(formerly Section 438 CrPC)."
)
RECEIVER_NOTE = (
    "For reference: appointment of receivers is dealt with under Order 40 CPC; Order 39 CPC covers temporary "
    "injunctions and interlocutory orders."
)
INJUNCTION_NOTE = "For reference: temporary injunctions are dealt with under Order 39 CPC."

_ACT_PATTERNS = (
    ("CrPC", r"cr\.?\s?p\.?\s?c\b|code of criminal procedure(?:,?\s*1973)?"),
    ("IPC", r"i\.?p\.?c\b|indian penal code(?:,?\s*1860)?"),
    ("IEA", r"(?:indian\s+)?evidence act(?:,?\s*1872)?"),
    ("BNSS", r"b\.?n\.?s\.?s\b|bharatiya nagarik suraksha sanhita(?:,?\s*2023)?"),
    ("BNS", r"b\.?n\.?s\b|bharatiya nyaya sanhita(?:,?\s*2023)?"),
    ("BSA", r"b\.?s\.?a\b|bharatiya sakshya adhiniyam(?:,?\s*2023)?"),
)
_ACT_RES = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _ACT_PATTERNS]
_ACT = "(?:" + "|".join(pattern for _, pattern in _ACT_PATTERNS) + ")"
_SEC_NUM = r"\d+[A-Z]{0,2}(?:\(\d+\))*"
_SEC_WORD = r"(?:sections?|secs?\.|sec\b|s\.|u/s\.?)"
_SECTION_CITATION_RE = re.compile(
    rf"\b{_SEC_WORD}\s*(?P<n1>{_SEC_NUM}(?:\s*(?:,|and|or|&)\s*{_SEC_NUM})*)(?:\s*(?:of\s+)?(?:the\s+)?(?P<a1>{_ACT}))?"
    rf"|(?P<a2>{_ACT})(?:,?\s*\d{{4}})?,?\s*{_SEC_WORD}\s*(?P<n2>{_SEC_NUM})"
    rf"|\b(?P<n3>{_SEC_NUM})\s+(?:of\s+)?(?:the\s+)?(?P<a3>{_ACT})",
    re.IGNORECASE,
)
_SEC_NUM_RE = re.compile(_SEC_NUM, re.IGNORECASE)
_REPEALED_SUCCESSOR = {"CrPC": "BNSS", "IPC": "BNS", "IEA": "BSA"}
_ACT_LABEL = {"CrPC": "CrPC", "IPC": "IPC", "IEA": "Evidence Act", "BNSS": "BNSS", "BNS": "BNS", "BSA": "BSA"}
# Only widely published correspondences; anything else is marked as the old
# provision without a new number.
_RENUMBERED = {
    "CrPC": {
        "125": "144", "144": "163", "154": "173", "156": "175", "161": "180", "164": "183", "167": "187",
        "197": "218", "200": "223", "313": "351", "320": "359", "436": "478", "436A": "479", "437": "480",
        "438": "482", "439": "483", "482": "528",
    },
    "IPC": {
        "34": "3(5)", "120B": "61", "302": "103", "304": "105", "304A": "106", "304B": "80", "307": "109",
        "323": "115", "354": "74", "376": "64", "379": "303", "406": "316", "420": "318", "498A": "85",
        "506": "351", "509": "79",
    },
    "IEA": {"65B": "63"},
}
_HISTORICAL_FRAMING_RE = re.compile(
    r"\b(?:formerly|earlier|previously|erstwhile|old(?:er)?|repealed|replac\w*|supersed\w*|succeeded|"
    r"prior to|used to|pre-july|corresponding|corresponds|equivalent)\b|\bbefore\b[^.]{0,20}\b2024\b",
    re.IGNORECASE,
)
_ORDER_RE = re.compile(r"\b[Oo]rder\s+(\d{1,2})\b|\b(?:Order|ORDER)\s+([IVXL]{1,7})\b|\bO\.\s?(\d{1,2})\b")
# A sentence that continues the previous one's subject ("It also ...").
_ANAPHORIC_START_RE = re.compile(
    r"^\s*(?:it|this|these|they|the order|under (?:it|this|the same)|the same)\b", re.IGNORECASE,
)
# (topic, kind, allowed citations, correction note). For sections, an
# act-less number is read as the act it's allowed under ("Section 438" in an
# anticipatory-bail sentence is the CrPC one).
_PROVISION_RULES = (
    (re.compile(r"\banticipatory bail\b", re.IGNORECASE), "section",
     {("BNSS", "482"), ("CrPC", "438")}, ANTICIPATORY_BAIL_NOTE),
    (re.compile(r"\breceivers?(?:ship)?\b", re.IGNORECASE), "order", {40}, RECEIVER_NOTE),
    (re.compile(r"\b(?:temporary|interim|ad[- ]interim)\s+injunctions?\b", re.IGNORECASE), "order", {39},
     INJUNCTION_NOTE),
)
_VERIFICATION_CLAIM_RE = re.compile(
    r"\bI(?:'ve|’ve| have)?\s+(?:verified|confirmed|checked|cross-checked)\b"
    r"|\b(?:has|have) been (?:verified|confirmed)\b"
    r"|\b(?:verified|confirmed) (?:as|to be) (?:current|accurate|correct|up[- ]to[- ]date)\b"
    r"|\bcurrent,?\s+verified\b|\bofficially (?:verified|confirmed)\b"
    r"|\b(?:100%|completely|fully|definitely) (?:accurate|correct|verified|up[- ]to[- ]date)\b"
    r"|\bguaranteed to be (?:current|accurate|correct)\b",
    re.IGNORECASE,
)
_CURRENT_LAW_QUESTION_RE = re.compile(
    r"\b(?:current(?:ly)?|latest|now|today|recent(?:ly)?|amend\w*|new law|in force|still (?:valid|applicable)|"
    r"up[- ]to[- ]date|as of)\b",
    re.IGNORECASE,
)
_CURRENT_LAW_ANSWER_RE = re.compile(r"\b(?:amend\w*|latest|recent(?:ly)?)\b", re.IGNORECASE)


def _act_key(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for name, pattern in _ACT_RES:
        if pattern.fullmatch(text.strip()):
            return name
    return None


def _base_section(number: str) -> str:
    return number.split("(")[0].upper()


def _section_citations(sentence: str) -> List[dict]:
    citations = []
    for m in _SECTION_CITATION_RE.finditer(sentence):
        numbers = m.group("n1") or m.group("n2") or m.group("n3")
        citations.append({
            "start": m.start(), "end": m.end(),
            "numbers": [_base_section(n) for n in _SEC_NUM_RE.findall(numbers)],
            "act": _act_key(m.group("a1") or m.group("a2") or m.group("a3")),
        })
    return citations


def _roman_to_int(value: str) -> int:
    numerals = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for i, ch in enumerate(value):
        n = numerals[ch]
        total += -n if i + 1 < len(value) and numerals[value[i + 1]] > n else n
    return total


def _orders(sentence: str) -> List[int]:
    return [int(a or c) if (a or c) else _roman_to_int(b) for a, b, c in _ORDER_RE.findall(sentence)]


def _old_provision_label(act: str, numbers: List[str]) -> str:
    successor = _REPEALED_SUCCESSOR[act]
    label = _ACT_LABEL[act] + (" provision" if len(numbers) == 1 else " provisions")
    mapped = [_RENUMBERED[act].get(n) for n in numbers]
    if all(mapped):
        word = "Section" if len(mapped) == 1 else "Sections"
        listed = mapped[0] if len(mapped) == 1 else ", ".join(mapped[:-1]) + " and " + mapped[-1]
        return f" (pre-July 2024 {label}; now {word} {listed} {successor})"
    return f" (pre-July 2024 {label}, since replaced by the {successor})"


def _check_provisions(sentence: str, context: dict) -> Tuple[Optional[str], List[str]]:
    """Returns (sentence, correction notes); sentence is None when it ties a
    known remedy to the wrong provision. `context` carries the previous
    sentence's topics and Order across sentences ("It also covers ...")."""
    citations = _section_citations(sentence)
    orders = _orders(sentence)
    anaphoric = bool(_ANAPHORIC_START_RE.match(sentence))
    topics_here = {i for i, rule in enumerate(_PROVISION_RULES) if rule[0].search(sentence)}
    topics = topics_here | (context["topics"] if anaphoric else set())
    effective_orders = orders or (context["orders"] if anaphoric else [])
    context["topics"] = topics
    context["orders"] = effective_orders

    # Act-less section numbers take the act they're allowed under for the topic.
    for citation in citations:
        if citation["act"] is None:
            for i in topics:
                _, kind, allowed, _ = _PROVISION_RULES[i]
                if kind == "section":
                    acts = {act for act, num in allowed if num in citation["numbers"]}
                    if len(acts) == 1:
                        citation["act"] = acts.pop()

    failed = []
    for i in sorted(topics):
        _, kind, allowed, note = _PROVISION_RULES[i]
        if kind == "order":
            if effective_orders and not any(o in allowed for o in effective_orders):
                failed.append(note)
        else:
            judged = [(c["act"], n) for c in citations if c["act"] in {a for a, _ in allowed} for n in c["numbers"]]
            if judged and not any(pair in allowed for pair in judged):
                failed.append(note)

    # "Section X BNSS (formerly Section Y CrPC)" must be a known pairing.
    for old_act, new_act in _REPEALED_SUCCESSOR.items():
        old = [n for c in citations if c["act"] == old_act for n in c["numbers"]]
        new = [n for c in citations if c["act"] == new_act for n in c["numbers"]]
        if len(old) == 1 and len(new) == 1:
            expected = _RENUMBERED[old_act].get(old[0])
            if expected is not None and _base_section(expected) != new[0]:
                failed.append(next((_PROVISION_RULES[i][3] for i in sorted(topics)), PARTIAL_ANSWER_NOTE))
    if failed:
        return None, list(dict.fromkeys(failed))

    # Mark repealed-code sections cited as if current.
    framed = _HISTORICAL_FRAMING_RE.search(sentence) or any(
        c["act"] in _REPEALED_SUCCESSOR.values() for c in citations)
    if not framed:
        for citation in reversed(citations):
            if citation["act"] in _REPEALED_SUCCESSOR:
                label = _old_provision_label(citation["act"], citation["numbers"])
                sentence = sentence[:citation["end"]] + label + sentence[citation["end"]:]
    return sentence, []


def guard_general_answer(answer: str, legal: bool, question: str = "",
                         verified_markers: frozenset = frozenset()) -> str:
    """No retrieved evidence backs this answer, so: drop CourtBazaar-specific
    claims, unverifiable case citations, long quotations and claims of
    verification; mark repealed-code sections as old and correct known
    wrong provisions; qualify legal figures (sections, statutes, time limits,
    amounts) and statistics as unverified.

    `verified_markers` are the "[n]" markers of a web answer's official-source
    citations (llm_service.generate_web_answer): a sentence naming a case is
    kept only when it carries one of them."""
    lines = []
    kept_count = dropped_courtbazaar = dropped_other = 0
    corrections: List[str] = []
    context = {"topics": set(), "orders": []}
    skipping = False
    for marker, sentences in _lines(answer):
        if _is_heading(marker) or marker == DIVIDER_MARKER:
            skipping = False
        elif skipping:
            # Same rule as validate_grounded_answer: a removed heading takes
            # the verbless items written under it.
            dropped_other += sum(1 for s in sentences if not _FINITE_VERB_RE.search(s))
            sentences = [s for s in sentences if _FINITE_VERB_RE.search(s)]
        kept: List[str] = []
        for sentence in sentences:
            if _COURTBAZAAR_TERM_RE.search(sentence) and _COURTBAZAAR_FACT_RE.search(sentence):
                dropped_courtbazaar += 1
                continue
            unsourced_case = (_CASE_CITATION_RE.search(sentence)
                              and not any(m in sentence for m in verified_markers))
            if unsourced_case or _LONG_QUOTE_RE.search(sentence) or _VERIFICATION_CLAIM_RE.search(sentence):
                dropped_other += 1
                continue
            checked, notes = _check_provisions(sentence, context)
            if checked is None:
                corrections += [n for n in notes if n not in corrections]
                dropped_other += 1
                continue
            kept.append(checked)
        kept_count += len(kept)
        if _is_heading(marker) and sentences and not kept:
            skipping = True
        lines.append((marker, kept))
    corrections = [n for n in corrections if n != PARTIAL_ANSWER_NOTE] + (
        [PARTIAL_ANSWER_NOTE] if PARTIAL_ANSWER_NOTE in corrections else [])
    if not kept_count and not corrections:
        if dropped_courtbazaar:
            return UNVERIFIED_COURTBAZAAR_MESSAGE
        return UNVERIFIED_LEGAL_MESSAGE if legal else UNVERIFIED_GENERAL_MESSAGE
    result = _rebuild(lines)
    checked_text = result + " " + " ".join(corrections)
    legal_content = legal or bool(_section_citations(checked_text) or _orders(checked_text))
    notes = list(corrections)
    if dropped_courtbazaar:
        notes.append(UNVERIFIED_COURTBAZAAR_MESSAGE)
    if legal_content and (_CURRENT_LAW_QUESTION_RE.search(question or "")
                          or _CURRENT_LAW_ANSWER_RE.search(result)):
        notes.append(CURRENT_LAW_NOTE)
    elif legal_content and (_LEGAL_FIGURE_RE.search(checked_text) or _LEGAL_FIGURE_WORDS_RE.search(checked_text)
                            or _STATUTE_NAME_RE.search(checked_text)):
        notes.append(LEGAL_VERIFY_NOTE)
    elif not legal and _STATISTIC_RE.search(result):
        notes.append(GENERAL_VERIFY_NOTE)
    if dropped_other and not notes:
        notes.append(PARTIAL_ANSWER_NOTE)
    if not result:
        return " ".join(notes)
    return result + ("\n\n" + " ".join(notes) if notes else "")


# A web-search answer must be a final answer: never the model's offer to search
# again or more broadly, a question about which search to run, or talk about
# its tools and domain filter.
_SEARCH_META_RE = re.compile(
    r"\b(?:would you like me to|do you want me to|shall I|should I|want me to)\b"
    r"|\bI can (?:also )?(?:try|search|run|re-?run|fetch|pull|look|check|retrieve)\b"
    r"|\bwhich (?:do|would) you prefer\b|\bwhich (?:option|approach) (?:do|would) you\b"
    r"|\b(?:search tool|another search|(?:search|look) (?:more )?broadly|broader search|faster results"
    r"|law[- ]reporting sites?|web search)\b"
    # Bare "gov.in"/"nic.in" (the filter), not a site such as indiacode.nic.in.
    r"|(?<![\w.])(?:gov|nic)\.in\b",
    re.IGNORECASE,
)
_OPTIONS_LEAD_RE = re.compile(r"^(?:I can|Options?|You can choose)\s*:?$", re.IGNORECASE)


def strip_search_meta(answer: str) -> str:
    """Removes sentences about how to search (see _SEARCH_META_RE), keeping
    the answer's line/list structure."""
    lines = [(prefix, [s for s in sentences if not _SEARCH_META_RE.search(s) and not _OPTIONS_LEAD_RE.match(s)])
             for prefix, sentences in _lines(answer)]
    return _rebuild(lines)


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
    r"|\bmy (?:system prompt|instructions) (?:is|are|says?)\b|\bhere (?:is|are) my (?:system prompt|instructions)\b"
    # A paraphrased disclosure of the hidden setup ("My instructions tell me
    # to ...", "I've been programmed to ...") is as much a leak as a quote.
    r"|\bmy (?:system prompt|system instructions|instructions|hidden rules|internal rules|developer message|"
    r"configuration) (?:tells?|says?|states?|requires?|instructs?|direct|directs|asks?)\b"
    r"|\bI(?:'ve| have)? been (?:instructed|programmed|configured|prompted) to\b"
    r"|\bI (?:was|am) (?:instructed|programmed|configured|prompted) to\b",
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
