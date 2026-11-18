"""The Settings answer language is added after the mode instruction and never
touches the master prompt (prompt_builder.LANGUAGE_INSTRUCTIONS)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ai_chat  # noqa: E402
import prompt_builder  # noqa: E402


def _texts(**kwargs):
    return [m["content"] for m in prompt_builder.build_legal_system_messages("Arbitration", **kwargs)]


def test_language_line_follows_the_mode_instruction_and_never_replaces_the_master_prompt():
    base = _texts(mode="lawyer", intent="qa")
    for language in ("en", "hi", "hinglish"):
        texts = _texts(mode="lawyer", intent="qa", language=language)
        assert texts[0] == prompt_builder.master_prompt() == base[0]  # first and unchanged
        mode_at = texts.index(prompt_builder.MODE_INSTRUCTIONS["lawyer"])
        assert texts[mode_at + 1] == prompt_builder.LANGUAGE_INSTRUCTIONS[language]
        assert texts[:mode_at + 1] + texts[mode_at + 2:] == base  # only added, nothing else moved
        assert prompt_builder.master_prompt() not in texts[1:]
    assert _texts(mode="layman", language="auto") == _texts(mode="layman")  # auto: today's prompt exactly
    assert _texts(mode="layman", language="klingon") == _texts(mode="layman")  # unknown: ignored


def test_the_chat_route_passes_the_language_to_the_document_prompt(monkeypatch):
    seen = {}
    real = prompt_builder.build_legal_system_messages

    def spy(subject, mode, intent="qa", language="auto"):
        seen["language"] = language
        return real(subject, mode, intent, language)

    async def fake(messages, **kwargs):
        seen["messages"] = [m["content"] for m in messages if m["role"] == "system"]
        return {"ok": True, "text": "Answer.", "sources": []}
    import llm_service
    monkeypatch.setattr(prompt_builder, "build_legal_system_messages", spy)
    monkeypatch.setattr(llm_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_service, "generate_response", fake)

    class Coll:
        async def find_one(self, *a, **k): return None
        async def insert_one(self, *a, **k): return None
        async def update_one(self, *a, **k): return None
        def find(self, *a, **k): return self
        def sort(self, *a, **k): return self
        def limit(self, *a, **k): return self
        async def to_list(self, *a, **k): return []

    class DB:
        def __getattr__(self, name): return Coll()

    asyncio.run(ai_chat.handle_chat_message(DB(), None, "What do the DIAC Rules say about appointment of arbitrators?",
                                            None, client_ip="203.0.113.9", language="hi"))
    assert seen["language"] == "hi"
    assert seen["messages"][0] == prompt_builder.master_prompt()
    assert prompt_builder.LANGUAGE_INSTRUCTIONS["hi"] in seen["messages"]


import answer_guard  # noqa: E402

EVIDENCE = ("[Source: DIAC Rules | Rule 8.1 | DIAC (Arbitration Proceedings) Rules, 2023]\n"
            "8.1 Where the parties have not agreed on the procedure, the Chairperson shall appoint the arbitrator "
            "within 15 days of the receipt of the request for appointment.")
PROVISIONS = {"8.1": EVIDENCE.split("\n", 1)[1]}


def _card(text, title="नियुक्ति", badge="Rule 8.1"):
    return {"status": "answered", "direct": None, "summary": "मध्यस्थ की नियुक्ति अध्यक्ष करते हैं।", "follow_up": "",
            "points": [{"title": title, "text": text, "badge": badge, "icon": "rule", "tone": "neutral", "cite": [1]}]}


def _kept(text, language, **kw):
    return answer_guard.validate_answer_card(_card(text, **kw), EVIDENCE, PROVISIONS, language=language) is not None


def test_hindi_and_hinglish_points_must_cite_a_retrieved_provision_and_match_its_figures():
    # Supported, in either digit system, and in Hinglish.
    assert _kept("नियम 8.1 के अनुसार, अध्यक्ष 15 दिनों के भीतर मध्यस्थ की नियुक्ति करेंगे।", "hi")
    assert _kept("नियम 8.1 के अनुसार, अध्यक्ष १५ दिनों के भीतर मध्यस्थ की नियुक्ति करेंगे।", "hi")
    assert _kept("Rule 8.1 ke hisaab se, Chairperson 15 din ke andar arbitrator appoint karenge.", "hinglish")
    # Unsupported: a figure the source doesn't have, a provision that wasn't retrieved, no provision at all.
    assert not _kept("नियम 8.1 के अनुसार, अध्यक्ष 7 दिनों के भीतर नियुक्ति करेंगे।", "hi")
    assert not _kept("नियम 9.2 के अनुसार, अध्यक्ष 15 दिनों में नियुक्ति करेंगे।", "hi", badge="Rule 9.2")
    assert not _kept("मध्यस्थ की नियुक्ति हमेशा सर्वोच्च न्यायालय करता है।", "hi", title="सर्वोच्च न्यायालय", badge="")


def test_only_the_unsupported_point_is_dropped_and_devanagari_digits_are_shown_as_figures():
    card = _card("नियम 8.1 के अनुसार, अध्यक्ष १५ दिनों के भीतर नियुक्ति करेंगे।")
    card["points"].append({"title": "शुल्क", "text": "कोई शुल्क नहीं लगता।", "badge": "", "icon": "info", "tone": "neutral", "cite": []})
    out = answer_guard.validate_answer_card(card, EVIDENCE, PROVISIONS, language="hi")
    assert [p["title"] for p in out["points"]] == ["नियुक्ति"]
    assert "15" in out["points"][0]["text"]


def test_english_answers_keep_the_english_wording_checks():
    english = "Under Rule 8.1, the Chairperson shall appoint the arbitrator within 15 days of the request."
    assert _kept(english, "auto", title="Appointment by the Chairperson")
    assert _kept(english, "en", title="Appointment by the Chairperson")
    # On "auto" a Hindi answer (Hindi question) is recognised by its script and checked the Hindi way,
    # so unsupported Devanagari prose no longer slips past the English word checks.
    hindi_unsupported = "मध्यस्थ की नियुक्ति हमेशा सर्वोच्च न्यायालय करता है।"
    assert not _kept(hindi_unsupported, "auto", title="सर्वोच्च न्यायालय", badge="")
    assert _kept("नियम 8.1 के अनुसार, अध्यक्ष 15 दिनों के भीतर नियुक्ति करेंगे।", "auto")


def test_the_language_setting_is_the_last_instruction_before_the_question():
    import llm_service
    msgs = [{"role": "system", "content": prompt_builder.master_prompt()},
            {"role": "user", "content": "<untrusted_document_excerpts>...</untrusted_document_excerpts>"},
            {"role": "system", "content": "Keep the document's own wording."},
            {"role": "user", "content": "What do the DIAC Rules say about the appointment of arbitrators?"}]
    for language in ("en", "hi", "hinglish"):
        out = llm_service.with_language(msgs, language)
        assert out[:-1][:3] == msgs[:3] and out[-1] == msgs[-1]  # only inserted, master prompt untouched
        assert out[-2] == {"role": "system", "content": prompt_builder.language_reminder(language)}
        assert out[-2]["content"].startswith(prompt_builder.LANGUAGE_INSTRUCTIONS[language])
    assert llm_service.with_language(msgs, "auto") == msgs


def test_card_and_plain_requests_both_end_with_the_language_setting(monkeypatch):
    """The card note ("keep the document's words") must not come after the language line."""
    import llm_service
    from types import SimpleNamespace
    seen = []

    async def create(**kwargs):
        seen.append(kwargs)
        raise RuntimeError("stop after capturing the request")

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    msgs = [{"role": "system", "content": prompt_builder.master_prompt()},
            {"role": "user", "content": "What do the DIAC Rules say about the appointment of arbitrators?"}]
    try:
        asyncio.run(llm_service._card_answer(client, msgs, "[Source: x | Rule 8]\n8. Text.", ["x"], language="hi"))
    except RuntimeError:
        pass
    request = seen[0]["input"]
    assert request[-1]["content"] == msgs[-1]["content"]
    assert request[-2]["content"] == prompt_builder.language_reminder("hi")
    assert any("SOURCES:" in m["content"] for m in request[:-2])  # card note sits before it
    assert prompt_builder.language_reminder("hi") in prompt_builder.protected_texts()
