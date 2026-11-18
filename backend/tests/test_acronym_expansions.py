"""A bracketed full form after an acronym survives only when the sources say it
(answer_guard.strip_invented_expansions), in every language."""
import answer_guard
import kb_registry

KNOWN = kb_registry.institution_names()


def strip(text, sources=()):
    return answer_guard.strip_invented_expansions(text, list(sources), KNOWN)


def test_the_reported_inventions_are_removed_in_any_language_leaving_the_acronym():
    # Real outputs: a Hindi and an English full form the MCIA Rules never give.
    for invented in ("मदीर परामर्श इंदौर अधिवक्ता", "महाद्वीपीय मध्यस्थता संस्थान",
                     "Mediation and Conciliation Institute of India"):
        text, removed = strip(f"यह दस्तावेज़ MCIA ({invented}) के नियमों को प्रस्तुत करता है।")
        assert text == "यह दस्तावेज़ MCIA के नियमों को प्रस्तुत करता है।"
        assert removed == [f"MCIA ({invented})"]


def test_a_full_form_in_the_sources_or_the_registry_is_kept():
    assert strip("MCIA (Mumbai Centre for International Arbitration) rules")[1] == []  # the registry's own name
    assert strip("The ABC (Arbitration Bar Council) rules", ["... the arbitration bar council may ..."])[1] == []
    # Any 2-6 letter all-caps token, not only the six institutions.
    assert strip("The ABC (Arbitration Bar Council) rules") == ("The ABC rules", ["ABC (Arbitration Bar Council)"])


def test_citations_in_brackets_are_not_full_forms():
    for text in ("DIAC (Rule 8.6) applies", "MCIA (MCIA-Rules-2025.pdf, page 3)", "ICC (Article 31)"):
        assert strip(text) == (text, [])


def test_nothing_is_substituted_and_ordinary_text_is_untouched():
    assert strip("SIAC (Singapore Arbitration Court) rules")[0] == "SIAC rules"  # never "corrected"
    assert strip("Plain words (in brackets) and Rule 8.6.") == ("Plain words (in brackets) and Rule 8.6.", [])
