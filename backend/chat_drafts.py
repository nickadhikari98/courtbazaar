"""Drafts in Instant Legal Help: three document types, for signed-in users.

A draft is a fixed CourtBazaar template (its facts are [Bracketed placeholders]
the user fills in) plus a "Legal basis" section the model writes from the
retrieved knowledge-base text. That section goes through the same
llm_service.generate_response path as any document answer, so every legal
statement is checked against the retrieved text and unsupported ones are
dropped. The template's own reliance on its anchor provision (Section 21,
Section 11, or the institution's rules) must be among the verified citations,
or no draft is produced.

Filled placeholder values never reach the model: the page sends them only to
the download endpoint, which substitutes them into the stored template text
(never into the legal basis or the citations) and renders DOCX or PDF.
"""
import io
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from fastapi import HTTPException

import answer_guard
import kb_registry
import llm_service
import prompt_builder

GUEST_MESSAGE = "Sign in to create drafts. Drafting is available to logged-in users only."
DRAFT_NOT_FOUND = "Draft not found."
PDF_UNAVAILABLE = "PDF isn't available for Hindi drafts yet. Download the Word file instead."
MAX_VALUE_CHARS = 500
SUPPORTED_INSTITUTIONS = ("DIAC", "ICA", "MCIA")
PLACEHOLDER_RE = re.compile(r"\[([^\[\]\n]{1,80})\]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DISCLAIMER = {
    "en": "Draft for review by a qualified advocate. This is not legal advice.",
    "hi": "यह एक ड्राफ्ट है, जिसकी समीक्षा किसी योग्य अधिवक्ता से कराई जानी चाहिए। यह कानूनी सलाह नहीं है।",
    "hinglish": "Yeh ek draft hai jise kisi qualified advocate se review karwana zaroori hai. Yeh legal advice nahi hai.",
}
HEADINGS = {
    "en": ("Legal basis", "Provisions relied on"),
    "hi": ("कानूनी आधार", "जिन प्रावधानों पर भरोसा किया गया"),
    "hinglish": ("Legal basis", "Provisions relied on"),
}
PARTIAL_NOTE = "Statements the approved sources don't support were left out of the legal basis."

# Search text per type: what the provision says about this document, not the user's words.
TYPES = {
    "section_21_notice": {
        "name": "Notice invoking arbitration under Section 21 of the Arbitration and Conciliation Act, 1996",
        "stem": "notice-invoking-arbitration-section-21",
        "anchor": "21",
        "query": "Section 21 commencement of arbitral proceedings request for the dispute to be referred to "
                 "arbitration received by the respondent",
    },
    "section_11_application": {
        "name": "Application for appointment of an arbitrator under Section 11",
        "stem": "application-appointment-of-arbitrator-section-11",
        "anchor": "11",
        "query": "Section 11 appointment of arbitrators failure to appoint within thirty days request to the "
                 "Supreme Court or High Court to take the necessary measure",
    },
    "institution_request": {
        "name": "Request for arbitration to an institution (DIAC, ICA or MCIA)",
        "stem": "request-for-arbitration",
        "anchor": None,
        "query": "request for arbitration commencement of arbitration contents of the request filing fee "
                 "registration notice to the respondent",
    },
}

_S11_RE = re.compile(r"\b(?:section|sec\.?|s\.)\s*11\b|\bappoint\w*\b.{0,40}\barbitrat\w*|\barbitrat\w*\b.{0,20}\bappoint",
                     re.IGNORECASE)
_S21_RE = re.compile(r"\b(?:section|sec\.?|s\.)\s*21\b|\binvok\w*\b.{0,40}\barbitrat\w*|\barbitrat\w*\b.{0,40}\bnotice\b"
                     r"|\bnotice\b.{0,40}\barbitrat\w*", re.IGNORECASE)
_REQUEST_RE = re.compile(r"\brequest for arbitration\b", re.IGNORECASE)
_CLOSEST_S11_RE = re.compile(r"\b(?:court|petition|application|appoint\w*)\b", re.IGNORECASE)
_CLOSEST_INSTITUTION_RE = re.compile(r"\b(?:institution|centre|center|council|rules|registrar|request)\b", re.IGNORECASE)


def classify(text: str) -> Tuple[Optional[str], Optional[str]]:
    """(type, institution) for a supported draft; (None, closest type) otherwise.
    "institution_request" with institution None means the institution is missing."""
    named = kb_registry.detect_institutions(text) - {kb_registry.ACT}
    if _S11_RE.search(text):
        return "section_11_application", None
    if named:
        inst = next((c for c in SUPPORTED_INSTITUTIONS if c in named), None)
        return ("institution_request", inst) if inst else (None, "institution_request")
    if _S21_RE.search(text):
        return "section_21_notice", None
    if _REQUEST_RE.search(text):
        return "institution_request", None
    if _CLOSEST_S11_RE.search(text):
        return None, "section_11_application"
    return None, "institution_request" if _CLOSEST_INSTITUTION_RE.search(text) else "section_21_notice"


def supported_message(closest: str, unsupported_institution: bool = False) -> str:
    lines = "\n".join(f"{i}. {t['name']}" for i, t in enumerate(TYPES.values(), 1))
    lead = ("I can prepare a request for arbitration only for DIAC, ICA or MCIA."
            if unsupported_institution else "I can't draft that kind of document yet.")
    return (f"{lead} I can draft these three:\n\n{lines}\n\n"
            f"The closest to what you asked for is: {TYPES[closest]['name']}. Ask for it by name and I'll prepare it.")


# A draft request that mentions arbitration (or an institution) gets the closest type; anything else is
# outside the knowledge base. shortcut: keyword rule, so a Hindi phrasing of "arbitration" reads as outside.
_ARBITRATION_RE = re.compile(r"\barbitra\w*|\btribunal\b|\bawards?\b|\ba\s*&\s*c act\b", re.IGNORECASE)


def is_arbitration_request(text: str) -> bool:
    return bool(_ARBITRATION_RE.search(text) or kb_registry.detect_institutions(text) - {kb_registry.ACT})


def out_of_scope_message() -> str:
    lines = "\n".join(f"{i}. {t['name']}" for i, t in enumerate(TYPES.values(), 1))
    return ("I can't draft that. The knowledge base covers Indian arbitration law, and these are the drafts "
            f"I can prepare:\n\n{lines}")


INSTITUTION_MISSING_MESSAGE = ("Which institution should the request for arbitration go to: DIAC, ICA or MCIA? "
                               "Ask again naming it, for example \"Draft a request for arbitration to MCIA\".")


# ---- Templates -------------------------------------------------------------
# (style, text). Placeholders stay in English in every language so one field
# fills every position; provision labels and names stay as the source writes them.
# "{inst}" / "{rules}" are the institution's acronym and its rules' title.

def _template(dtype: str, lang: str) -> List[Tuple[str, str]]:
    t = _TEMPLATES[dtype]
    return t.get(lang) or t["en"]


_TEMPLATES: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
    "section_21_notice": {
        "en": [
            ("title", "Notice invoking arbitration under Section 21 of the Arbitration and Conciliation Act, 1996"),
            ("para", "Date: [Date of notice]"),
            ("para", "To: [Respondent name], [Respondent address]"),
            ("para", "From: [Claimant name], [Claimant address]"),
            ("para", "1. The Claimant and the Respondent are parties to [Name of the agreement] dated [Date of the agreement]."),
            ("para", "2. Clause [Clause number of the arbitration agreement] of that agreement provides that disputes between the parties are to be resolved by arbitration."),
            ("para", "3. Disputes have arisen between the parties: [Description of the disputes]."),
            ("para", "4. The Claimant claims [Amount claimed] and [Other relief claimed]."),
            ("para", "5. By this notice, the Claimant requests that the disputes described above be referred to arbitration under Section 21 of the Arbitration and Conciliation Act, 1996."),
            ("para", "6. For the appointment of the arbitral tribunal, the Claimant proposes: [Proposed arbitrator or appointment procedure under the agreement]."),
            ("grounds", ""),
            ("para", "For [Claimant name]"),
            ("para", "[Name and designation of the signatory]"),
            ("sources", ""),
        ],
        "hi": [
            ("title", "Arbitration and Conciliation Act, 1996 की Section 21 के अंतर्गत मध्यस्थता का आह्वान करने का नोटिस"),
            ("para", "दिनांक: [Date of notice]"),
            ("para", "प्रति: [Respondent name], [Respondent address]"),
            ("para", "प्रेषक: [Claimant name], [Claimant address]"),
            ("para", "1. दावेदार और प्रतिवादी [Date of the agreement] के [Name of the agreement] के पक्षकार हैं।"),
            ("para", "2. उस अनुबंध का Clause [Clause number of the arbitration agreement] यह प्रावधान करता है कि पक्षकारों के बीच विवादों का समाधान मध्यस्थता द्वारा किया जाएगा।"),
            ("para", "3. पक्षकारों के बीच विवाद उत्पन्न हुए हैं: [Description of the disputes]।"),
            ("para", "4. दावेदार [Amount claimed] और [Other relief claimed] का दावा करता है।"),
            ("para", "5. इस नोटिस द्वारा दावेदार अनुरोध करता है कि ऊपर वर्णित विवादों को Arbitration and Conciliation Act, 1996 की Section 21 के अंतर्गत मध्यस्थता के लिए भेजा जाए।"),
            ("para", "6. मध्यस्थ अधिकरण की नियुक्ति के लिए दावेदार प्रस्तावित करता है: [Proposed arbitrator or appointment procedure under the agreement]।"),
            ("grounds", ""),
            ("para", "कृते [Claimant name]"),
            ("para", "[Name and designation of the signatory]"),
            ("sources", ""),
        ],
        "hinglish": [
            ("title", "Arbitration and Conciliation Act, 1996 ki Section 21 ke tahat arbitration invoke karne ka notice"),
            ("para", "Date: [Date of notice]"),
            ("para", "To: [Respondent name], [Respondent address]"),
            ("para", "From: [Claimant name], [Claimant address]"),
            ("para", "1. Claimant aur Respondent [Date of the agreement] ke [Name of the agreement] ke parties hain."),
            ("para", "2. Us agreement ka Clause [Clause number of the arbitration agreement] kehta hai ki parties ke beech disputes arbitration se resolve honge."),
            ("para", "3. Parties ke beech disputes paida hue hain: [Description of the disputes]."),
            ("para", "4. Claimant [Amount claimed] aur [Other relief claimed] claim karta hai."),
            ("para", "5. Is notice ke zariye Claimant request karta hai ki upar diye gaye disputes Arbitration and Conciliation Act, 1996 ki Section 21 ke tahat arbitration ko refer kiye jaayein."),
            ("para", "6. Arbitral tribunal ki appointment ke liye Claimant propose karta hai: [Proposed arbitrator or appointment procedure under the agreement]."),
            ("grounds", ""),
            ("para", "For [Claimant name]"),
            ("para", "[Name and designation of the signatory]"),
            ("sources", ""),
        ],
    },
    "section_11_application": {
        "en": [
            ("title", "In the [Name of the court]"),
            ("para", "Arbitration Application No. [Case number] of [Year]"),
            ("para", "In the matter of an application under Section 11 of the Arbitration and Conciliation Act, 1996"),
            ("para", "[Applicant name], [Applicant address] ... Applicant"),
            ("para", "Versus"),
            ("para", "[Respondent name], [Respondent address] ... Respondent"),
            ("heading", "Application for appointment of an arbitrator under Section 11"),
            ("para", "1. The Applicant and the Respondent are parties to [Name of the agreement] dated [Date of the agreement]."),
            ("para", "2. Clause [Clause number of the arbitration agreement] of that agreement provides for arbitration and for the appointment of the arbitrator as follows: [Appointment procedure in the agreement]."),
            ("para", "3. Disputes have arisen between the parties: [Description of the disputes]."),
            ("para", "4. On [Date of the notice invoking arbitration], the Applicant sent the Respondent a notice invoking arbitration, which the Respondent received on [Date the notice was received]."),
            ("para", "5. The arbitrator has not been appointed: [What happened after the notice]."),
            ("grounds", ""),
            ("heading", "Prayer"),
            ("para", "The Applicant therefore prays that this Court take the necessary measure for the appointment of an arbitrator under Section 11 of the Arbitration and Conciliation Act, 1996, and pass any other order it considers fit."),
            ("para", "Place: [Place of filing]"),
            ("para", "Date: [Date of filing]"),
            ("para", "For [Applicant name]"),
            ("para", "[Name of the signatory or advocate]"),
            ("sources", ""),
        ],
        "hi": [
            ("title", "[Name of the court] के समक्ष"),
            ("para", "Arbitration Application No. [Case number] of [Year]"),
            ("para", "Arbitration and Conciliation Act, 1996 की Section 11 के अंतर्गत आवेदन के विषय में"),
            ("para", "[Applicant name], [Applicant address] ... आवेदक"),
            ("para", "बनाम"),
            ("para", "[Respondent name], [Respondent address] ... प्रतिवादी"),
            ("heading", "Section 11 के अंतर्गत मध्यस्थ की नियुक्ति के लिए आवेदन"),
            ("para", "1. आवेदक और प्रतिवादी [Date of the agreement] के [Name of the agreement] के पक्षकार हैं।"),
            ("para", "2. उस अनुबंध का Clause [Clause number of the arbitration agreement] मध्यस्थता और मध्यस्थ की नियुक्ति का प्रावधान इस प्रकार करता है: [Appointment procedure in the agreement]।"),
            ("para", "3. पक्षकारों के बीच विवाद उत्पन्न हुए हैं: [Description of the disputes]।"),
            ("para", "4. [Date of the notice invoking arbitration] को आवेदक ने प्रतिवादी को मध्यस्थता का आह्वान करने का नोटिस भेजा, जो प्रतिवादी को [Date the notice was received] को प्राप्त हुआ।"),
            ("para", "5. मध्यस्थ की नियुक्ति नहीं हुई है: [What happened after the notice]।"),
            ("grounds", ""),
            ("heading", "प्रार्थना"),
            ("para", "अतः आवेदक प्रार्थना करता है कि यह न्यायालय Arbitration and Conciliation Act, 1996 की Section 11 के अंतर्गत मध्यस्थ की नियुक्ति के लिए आवश्यक उपाय करे, और कोई अन्य आदेश पारित करे जो वह उचित समझे।"),
            ("para", "स्थान: [Place of filing]"),
            ("para", "दिनांक: [Date of filing]"),
            ("para", "कृते [Applicant name]"),
            ("para", "[Name of the signatory or advocate]"),
            ("sources", ""),
        ],
        "hinglish": [
            ("title", "[Name of the court] mein"),
            ("para", "Arbitration Application No. [Case number] of [Year]"),
            ("para", "Arbitration and Conciliation Act, 1996 ki Section 11 ke tahat application ke maamle mein"),
            ("para", "[Applicant name], [Applicant address] ... Applicant"),
            ("para", "Versus"),
            ("para", "[Respondent name], [Respondent address] ... Respondent"),
            ("heading", "Section 11 ke tahat arbitrator ki appointment ke liye application"),
            ("para", "1. Applicant aur Respondent [Date of the agreement] ke [Name of the agreement] ke parties hain."),
            ("para", "2. Us agreement ka Clause [Clause number of the arbitration agreement] arbitration aur arbitrator ki appointment ke liye yeh provide karta hai: [Appointment procedure in the agreement]."),
            ("para", "3. Parties ke beech disputes paida hue hain: [Description of the disputes]."),
            ("para", "4. [Date of the notice invoking arbitration] ko Applicant ne Respondent ko arbitration invoke karne ka notice bheja, jo Respondent ko [Date the notice was received] ko mila."),
            ("para", "5. Arbitrator ki appointment nahi hui hai: [What happened after the notice]."),
            ("grounds", ""),
            ("heading", "Prayer"),
            ("para", "Isliye Applicant prarthna karta hai ki yeh Court Arbitration and Conciliation Act, 1996 ki Section 11 ke tahat arbitrator ki appointment ke liye zaroori kadam uthaye, aur koi aur order pass kare jo use uchit lage."),
            ("para", "Place: [Place of filing]"),
            ("para", "Date: [Date of filing]"),
            ("para", "For [Applicant name]"),
            ("para", "[Name of the signatory or advocate]"),
            ("sources", ""),
        ],
    },
    "institution_request": {
        "en": [
            ("title", "Request for arbitration"),
            ("para", "Under the {rules}"),
            ("para", "To: {inst}, [Address of the institution]"),
            ("para", "Date: [Date of the request]"),
            ("para", "Claimant: [Claimant name], [Claimant address], [Claimant email]"),
            ("para", "Represented by: [Counsel name and contact details]"),
            ("para", "Respondent: [Respondent name], [Respondent address], [Respondent email]"),
            ("para", "1. The Claimant and the Respondent are parties to [Name of the agreement] dated [Date of the agreement]."),
            ("para", "2. Clause [Clause number of the arbitration agreement] of that agreement provides for arbitration: [Text of the arbitration clause]."),
            ("para", "3. Nature of the disputes: [Description of the disputes]."),
            ("para", "4. Relief claimed: [Amount claimed] and [Other relief claimed]."),
            ("para", "5. Number of arbitrators and any nominee: [Number of arbitrators and nominee]."),
            ("para", "6. Seat and language of the arbitration: [Seat of arbitration], [Language of arbitration]."),
            ("para", "7. The Claimant asks {inst} to register this request and commence the arbitration under the {rules}."),
            ("grounds", ""),
            ("para", "For [Claimant name]"),
            ("para", "[Name and designation of the signatory]"),
            ("sources", ""),
        ],
        "hi": [
            ("title", "मध्यस्थता के लिए अनुरोध"),
            ("para", "{rules} के अंतर्गत"),
            ("para", "प्रति: {inst}, [Address of the institution]"),
            ("para", "दिनांक: [Date of the request]"),
            ("para", "दावेदार: [Claimant name], [Claimant address], [Claimant email]"),
            ("para", "प्रतिनिधि: [Counsel name and contact details]"),
            ("para", "प्रतिवादी: [Respondent name], [Respondent address], [Respondent email]"),
            ("para", "1. दावेदार और प्रतिवादी [Date of the agreement] के [Name of the agreement] के पक्षकार हैं।"),
            ("para", "2. उस अनुबंध का Clause [Clause number of the arbitration agreement] मध्यस्थता का प्रावधान करता है: [Text of the arbitration clause]।"),
            ("para", "3. विवादों का स्वरूप: [Description of the disputes]।"),
            ("para", "4. मांगी गई राहत: [Amount claimed] और [Other relief claimed]।"),
            ("para", "5. मध्यस्थों की संख्या और कोई नामित मध्यस्थ: [Number of arbitrators and nominee]।"),
            ("para", "6. मध्यस्थता का स्थान (seat) और भाषा: [Seat of arbitration], [Language of arbitration]।"),
            ("para", "7. दावेदार {inst} से अनुरोध करता है कि इस अनुरोध को पंजीकृत करे और {rules} के अंतर्गत मध्यस्थता आरंभ करे।"),
            ("grounds", ""),
            ("para", "कृते [Claimant name]"),
            ("para", "[Name and designation of the signatory]"),
            ("sources", ""),
        ],
        "hinglish": [
            ("title", "Arbitration ke liye request"),
            ("para", "{rules} ke tahat"),
            ("para", "To: {inst}, [Address of the institution]"),
            ("para", "Date: [Date of the request]"),
            ("para", "Claimant: [Claimant name], [Claimant address], [Claimant email]"),
            ("para", "Represented by: [Counsel name and contact details]"),
            ("para", "Respondent: [Respondent name], [Respondent address], [Respondent email]"),
            ("para", "1. Claimant aur Respondent [Date of the agreement] ke [Name of the agreement] ke parties hain."),
            ("para", "2. Us agreement ka Clause [Clause number of the arbitration agreement] arbitration provide karta hai: [Text of the arbitration clause]."),
            ("para", "3. Disputes ka nature: [Description of the disputes]."),
            ("para", "4. Relief claimed: [Amount claimed] aur [Other relief claimed]."),
            ("para", "5. Arbitrators ki sankhya aur koi nominee: [Number of arbitrators and nominee]."),
            ("para", "6. Arbitration ki seat aur language: [Seat of arbitration], [Language of arbitration]."),
            ("para", "7. Claimant {inst} se request karta hai ki is request ko register kare aur {rules} ke tahat arbitration shuru kare."),
            ("grounds", ""),
            ("para", "For [Claimant name]"),
            ("para", "[Name and designation of the signatory]"),
            ("sources", ""),
        ],
    },
}


# ---- Building a draft ------------------------------------------------------

def _grounds(result: Dict[str, Any]) -> List[str]:
    """The verified legal statements, one paragraph each, without headings or the partial note."""
    card = result.get("answer")
    if card:
        # The summary restates the points (seen live), so it's used only when there are none.
        parts = [p.get("text") or "" for p in card.get("points") or []] or [card.get("summary") or ""]
    else:
        parts = (result.get("text") or "").splitlines()
    out = []
    for part in parts:
        line = part.strip()
        if not line or line.startswith("#") or line == "---" or answer_guard.PARTIAL_ANSWER_NOTE in line:
            continue
        line = re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", line).replace("**", "")
        if line not in out:
            out.append(line)
    return out


def citation_lines(citations: List[Dict[str, Any]]) -> List[str]:
    """Same parts the chat's source list shows: document, then its verified provisions."""
    lines = []
    for c in citations:
        rules = c.get("rules") or []
        title = c.get("title") or c.get("document") or ""
        lines.append(f"{title}: {c.get('label') or 'Rule'} {', '.join(rules)}" if rules else title)
    return lines


def _source_file(dtype: str, inst: Optional[str]) -> Optional[str]:
    return next(iter(kb_registry.files_for(inst if dtype == "institution_request" else kb_registry.ACT)), None)


def _anchor_cited(dtype: str, citations: List[Dict[str, Any]]) -> bool:
    anchor = TYPES[dtype]["anchor"]
    if anchor is None:
        return any(c.get("rules") for c in citations)
    return any(anchor in (c.get("rules") or []) and (c.get("label") or "").lower().startswith("section")
               for c in citations)


def build_blocks(dtype: str, lang: str, grounds: List[str], citations: List[Dict[str, Any]],
                 inst: Optional[str] = None, rules_title: str = "") -> List[Dict[str, Any]]:
    """The draft as blocks. `fill` marks template text whose placeholders the user may fill;
    the legal basis and the provisions are never filled."""
    basis, relied = HEADINGS.get(lang, HEADINGS["en"])
    blocks: List[Dict[str, Any]] = []
    for style, text in _template(dtype, lang):
        if style == "grounds":
            blocks.append({"style": "heading", "text": basis, "fill": False})
            blocks += [{"style": "para", "text": g, "fill": False} for g in grounds]
        elif style == "sources":
            blocks.append({"style": "heading", "text": relied, "fill": False})
            blocks += [{"style": "para", "text": line, "fill": False} for line in citation_lines(citations)]
        else:
            blocks.append({"style": style, "text": text.replace("{inst}", inst or "").replace("{rules}", rules_title),
                           "fill": True})
    return blocks


def plain_text(draft: Dict[str, Any], values: Optional[Dict[str, str]] = None) -> str:
    return "\n\n".join([draft["disclaimer"]] + [fill(b["text"], values) if b["fill"] else b["text"]
                                                for b in draft["blocks"]])


async def compose(text: str, language: str = "auto",
                  on_status: Optional[llm_service.StatusCallback] = None) -> Dict[str, Any]:
    """{"reply"} for a request that gets no draft, or {"reply", "draft", "citations", "grounding"}.
    Raises nothing for model failures: they come back as a reply with `error_code`."""
    dtype, extra = classify(text)
    if dtype is None:
        if not is_arbitration_request(text):
            return {"reply": out_of_scope_message()}
        return {"reply": supported_message(extra, unsupported_institution=bool(
            kb_registry.detect_institutions(text) - {kb_registry.ACT}))}
    if dtype == "institution_request" and extra is None:
        return {"reply": INSTITUTION_MISSING_MESSAGE}
    inst = extra
    source = _source_file(dtype, inst)
    if source is None:
        return {"reply": "The approved sources for this draft aren't available right now, so I haven't written one."}
    lang = language if language in ("en", "hi", "hinglish") else "en"
    messages = prompt_builder.build_legal_system_messages(prompt_builder.subject_for(source), "lawyer", "draft",
                                                          language)
    # A fixed question, not the user's words: details typed into the request never reach the model.
    messages.append({"role": "user", "content": f"What do the provisions say about a {TYPES[dtype]['name'].lower()}: "
                                                "who may make it, what it must contain, its time limits and what follows it?"})
    await llm_service.emit_status(on_status, "drafting", "Preparing the draft…")
    result = await llm_service.generate_response(
        messages, use_file_search=True, selected_source=source, on_status=on_status,
        retrieval_query=TYPES[dtype]["query"], **({"language": language} if language != "auto" else {}))
    label = kb_registry.display_label(source) or source
    if not result["ok"]:
        if result["error_code"] == llm_service.ERR_NO_CONTEXT:
            return {"reply": f"I couldn't find enough in the {label} to support this draft, so I haven't written one.",
                    "grounding": "insufficient", "degraded": True}
        return {"reply": None, "error_code": result["error_code"], "degraded": True}
    citations = result.get("citations") or []
    grounds = [g for g in _grounds(result) if not answer_guard.check_output(g, prompt_builder.protected_texts())[1]]
    if not grounds or not _anchor_cited(dtype, citations):
        anchor = TYPES[dtype]["anchor"]
        what = f"Section {anchor} in the {label}" if anchor else f"the provisions on a request for arbitration in the {label}"
        return {"reply": f"I couldn't confirm {what} from the approved sources, so I haven't written this draft.",
                "grounding": "insufficient", "degraded": True}
    now = datetime.now(timezone.utc)
    draft = {
        "draft_id": f"draft_{uuid.uuid4().hex[:16]}",
        "type": dtype,
        "language": lang,
        "title": TYPES[dtype]["name"] if dtype != "institution_request" else f"Request for arbitration to {inst}",
        "disclaimer": DISCLAIMER[lang],
        "blocks": build_blocks(dtype, lang, grounds, citations, inst, label),
        "file_stem": f"{TYPES[dtype]['stem']}{'-' + inst.lower() if inst else ''}_{now.date().isoformat()}",
        "pdf": lang != "hi",
        "note": PARTIAL_NOTE if result.get("partial") else None,
        "created_at": now.isoformat(),
    }
    return {"reply": plain_text(draft), "draft": draft, "citations": citations,
            "grounding": "partial" if result.get("partial") else "supported", "degraded": False}


# ---- Filling and files -----------------------------------------------------

def placeholders(draft: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for b in draft["blocks"]:
        if b["fill"]:
            names += [n for n in PLACEHOLDER_RE.findall(b["text"]) if n not in names]
    return names


def clean_values(draft: Dict[str, Any], values: Any) -> Dict[str, str]:
    """Only this draft's own placeholders, as trimmed single-paragraph text; anything else is ignored."""
    if not isinstance(values, dict):
        return {}
    allowed = set(placeholders(draft))
    out = {}
    for name, value in values.items():
        if name in allowed and isinstance(value, str):
            value = _CONTROL_RE.sub("", unicodedata.normalize("NFC", value)).replace("\r", "").strip()
            if len(value) > MAX_VALUE_CHARS:
                raise HTTPException(422, f"A field is longer than {MAX_VALUE_CHARS} characters.")
            if value:
                out[name] = value
    return out


def fill(text: str, values: Optional[Dict[str, str]]) -> str:
    """An empty field keeps its [placeholder], so the file shows what is still missing."""
    return PLACEHOLDER_RE.sub(lambda m: (values or {}).get(m.group(1)) or m.group(0), text)


def _filled_blocks(draft: Dict[str, Any], values: Dict[str, str]) -> List[Dict[str, Any]]:
    return [{**b, "text": fill(b["text"], values) if b["fill"] else b["text"]} for b in draft["blocks"]]


def render_docx(draft: Dict[str, Any], values: Dict[str, str]) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = Document()
    run = doc.add_paragraph().add_run(draft["disclaimer"])
    run.bold = run.italic = True
    for b in _filled_blocks(draft, values):
        if b["style"] == "title":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run(b["text"]).bold = True
        elif b["style"] == "heading":
            doc.add_paragraph().add_run(b["text"]).bold = True
        else:
            doc.add_paragraph(b["text"])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_pdf(draft: Dict[str, Any], values: Dict[str, str]) -> bytes:
    if not draft.get("pdf"):
        # shortcut: no Devanagari font or text shaping in the backend yet; add both before enabling Hindi PDFs.
        raise HTTPException(409, PDF_UNAVAILABLE)
    filled = _filled_blocks(draft, values)
    try:
        # The built-in font is WinAnsi (cp1252): anything else would print as boxes, e.g. a name in Devanagari.
        "\n".join([draft["disclaimer"], *(b["text"] for b in filled)]).replace("₹", "Rs. ").encode("cp1252")
    except UnicodeEncodeError:
        raise HTTPException(409, PDF_UNAVAILABLE)
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    base = getSampleStyleSheet()["Normal"]
    styles = {
        "para": ParagraphStyle("para", parent=base, fontSize=11, leading=15, spaceAfter=6),
        "heading": ParagraphStyle("heading", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=15,
                                  spaceBefore=8, spaceAfter=4),
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                                alignment=TA_CENTER, spaceAfter=10),
        "disclaimer": ParagraphStyle("disclaimer", parent=base, fontName="Helvetica-BoldOblique", fontSize=10,
                                     leading=13, spaceAfter=10),
    }

    def para(text: str, style: str) -> Paragraph:
        # shortcut: the built-in PDF font covers Latin text only; ₹ becomes "Rs." and other scripts won't render.
        return Paragraph(escape(text.replace("₹", "Rs. ")).replace("\n", "<br/>"), styles[style])

    flow = [para(draft["disclaimer"], "disclaimer"), Spacer(1, 4)]
    flow += [para(b["text"], b["style"] if b["style"] in styles else "para") for b in filled]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=draft["title"], leftMargin=60, rightMargin=60,
                      topMargin=56, bottomMargin=56).build(flow)
    return buf.getvalue()


MEDIA_TYPES = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "pdf": "application/pdf"}


async def ensure_indexes(db) -> None:
    await db.ai_chat_messages.create_index([("draft.draft_id", 1)], name="draft_id", sparse=True)


async def download(db, user: Optional[dict], draft_id: str, fmt: str, values: Any) -> Tuple[bytes, str, str]:
    """(file bytes, file name, media type) for the owner's draft with their values filled in."""
    user_id = user.get("user_id") if user else None
    if not user_id:
        raise HTTPException(403, GUEST_MESSAGE)
    if fmt not in MEDIA_TYPES:
        raise HTTPException(404, DRAFT_NOT_FOUND)
    msg = await db.ai_chat_messages.find_one({"draft.draft_id": draft_id}, {"_id": 0, "conversation_id": 1, "draft": 1})
    convo = msg and await db.ai_conversations.find_one({"conversation_id": msg["conversation_id"]}, {"_id": 0, "user_id": 1})
    if not convo or convo.get("user_id") != user_id:
        raise HTTPException(404, DRAFT_NOT_FOUND)  # same answer for missing and not yours
    draft = msg["draft"]
    clean = clean_values(draft, values)
    data = render_docx(draft, clean) if fmt == "docx" else render_pdf(draft, clean)
    return data, f"{draft['file_stem']}.{fmt}", MEDIA_TYPES[fmt]
