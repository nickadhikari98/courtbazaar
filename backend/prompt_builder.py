"""Server-only legal prompts for document answers: the Master Prompt, the
advocate role line, the reader mode and the task (intent) instruction.
Nothing here is ever sent to the browser or put in an API response."""
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import kb_registry

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
INTENTS = ("qa", "draft", "case_research", "document_analysis")

MODE_INSTRUCTIONS = {
    "layman": (
        "READER: a layperson. Use simple English, or Hinglish if the user writes in Hinglish (match their "
        "language). Keep it short, give a small everyday example where it helps, and explain any legal term the "
        "first time you use it."
    ),
    "lawyer": (
        "READER: a lawyer. Use precise legal terms and give section and rule numbers. Distinguish binding from "
        "persuasive authority, and state the limitations of the material relied on. When a provision you cite has "
        "a proviso (\"Provided that ...\") or an exception, state it with that provision."
    ),
}

# Checked in order; the first match wins. shortcut: keyword rules only, swap for a classifier if they misfire.
_INTENT_RES = (
    ("document_analysis", re.compile(
        r"\b(?:analy[sz]e|review|check|examine)\b.{0,40}\b(?:my|this|the attached|attached|uploaded)\b.{0,20}"
        r"\b(?:agreement|contract|clause|document|award|notice|petition|order)\b|\battached\b|\buploaded\b",
        re.IGNORECASE)),
    ("draft", re.compile(r"\b(?:draft|drafting|prepare|write|format|template)\b.{0,40}"
                         r"\b(?:notice|petition|application|agreement|clause|reply|statement|affidavit|letter)\b"
                         r"|\bdraft\b", re.IGNORECASE)),
    ("case_research", re.compile(
        r"\b(?:case ?laws?|judg(?:e)?ments?|precedents?|rulings?|citations?|landmark|decided cases?)\b"
        r"|\b(?:supreme|high) court\b.{0,30}\b(?:held|says|said|decided|view)\b|\bv(?:s)?\.\s", re.IGNORECASE)),
)


def detect_intent(text: str) -> str:
    return next((name for name, rx in _INTENT_RES if rx.search(text or "")), "qa")


@lru_cache(maxsize=1)
def master_prompt() -> str:
    path = Path(os.environ.get("MASTER_PROMPT_PATH") or _PROMPTS_DIR / "master_prompt.md")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def task_instruction(intent: str) -> str:
    return (_PROMPTS_DIR / "tasks" / f"{intent if intent in INTENTS else 'qa'}.md").read_text(encoding="utf-8").strip()


def subject_for(source: Optional[str]) -> str:
    """The law area of a KB file, from its registry record ("Arbitration" by default)."""
    recs = kb_registry.records_for_file(source) if source else None
    subject = next((r.get("subject") for r in recs or [] if r.get("subject")), None)
    return (subject or "arbitration").replace("_", " ").title()


def role_line(subject: str) -> str:
    return (f"Act as an Advocate having expertise in {subject} law in India. Answer as a careful legal research "
            "assistant: only from the retrieved CourtBazaar material, never as a substitute for a qualified advocate.")


# The reader's preferred answer language, from chat Settings. "auto" adds
# nothing (today's behaviour: the model follows the message). Each is a
# separate system message right after the mode instruction, so it can only
# add to the master prompt, never replace or reorder it.
# Never translated, transliterated or expanded, in any language: a Hindi answer once
# rendered MCIA as "MCIA (मदीर परामर्श इंदौर अधिवक्ता)", an invented full form.
NO_INVENTED_EXPANSION = ("Never invent a full form for an acronym: if the source doesn't spell it out, write the "
                         "acronym alone; if it does, use the source's own words. Never put words in brackets after "
                         "an acronym (\"MCIA (...)\") unless those exact words appear in the text you were given, "
                         "and never guess what an acronym stands for from its letters.")
NAMES_STAY_AS_SOURCE = (
    "Translate only the explanation, never a name or a number. Keep every proper noun exactly as the source "
    "writes it, in Latin script, untranslated and unexpanded: institution names and their acronyms (MCIA, DIAC, "
    "SIAC, ICC, LCIA, ICA), document titles, court names, party names and defined terms. "
    + NO_INVENTED_EXPANSION + " Keep provision labels and numbers in their source form, in English, so they match "
    "the citations: \"Rule 8.6\", \"Section 29A\", \"Article 31\", \"Appendix IV, Article 7\"."
)
LANGUAGE_INSTRUCTIONS = {
    "auto": None,
    "en": "Answer language: write the answer in English. " + NO_INVENTED_EXPANSION,
    "hi": "Answer language: write the answer in Hindi (Devanagari script). " + NAMES_STAY_AS_SOURCE,
    "hinglish": ("Answer language: write the answer in Hinglish (Hindi in Latin script, with English legal terms). "
                 + NAMES_STAY_AS_SOURCE),
}


# Repeated as the last instruction before the question (llm_service.with_language):
# the evidence and card instructions that come after the first language line say to
# keep "the document's own words", and that later, more specific instruction won,
# so a Hindi or Hinglish setting came back in English.
LANGUAGE_OVER_WORDING = (
    " This applies to every sentence of the answer, including where the instructions above say to keep the "
    "document's own words or wording: translate the meaning of that wording faithfully instead of copying it in "
    "English. Names, acronyms, defined terms and provision labels are not translated: they stay exactly as in the "
    "source."
)


def language_reminder(language: str) -> Optional[str]:
    line = LANGUAGE_INSTRUCTIONS.get(language)
    return line + LANGUAGE_OVER_WORDING if line else None


def build_legal_system_messages(subject: str = "Arbitration", mode: str = "layman",
                                intent: str = "qa", language: str = "auto") -> List[Dict[str, str]]:
    """Master prompt, role line, mode instruction, [language], task instruction — in that order."""
    language_line = LANGUAGE_INSTRUCTIONS.get(language)
    return [{"role": "system", "content": text} for text in (
        master_prompt(), role_line(subject), MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["layman"]),
        *([language_line] if language_line else []),
        task_instruction(intent),
    )]


def protected_texts() -> List[str]:
    """Every hidden legal instruction, for answer_guard.check_output."""
    return [master_prompt(), *MODE_INSTRUCTIONS.values(), *(task_instruction(i) for i in INTENTS),
            *(language_reminder(lang) for lang in LANGUAGE_INSTRUCTIONS if language_reminder(lang))]
