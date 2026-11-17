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
