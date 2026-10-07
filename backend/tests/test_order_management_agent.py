"""Order Management Agent — orchestration (order_management_agent.py).
Exercises the degrade-gracefully paths (no API key / timeout / model error)
and the tool-calling loop against a fake client, so these tests need no real
OpenAI API key or network access — same "best-effort, never propagate"
convention as hearings.check_pending_order_sheets/auto_release_stale_
verifications. The tool-dispatch test and the "hearing not found" test run
against a real local MongoDB (same conventions as the other test files).
"""
import asyncio
import json
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hearings  # noqa: E402
import order_agent_tools  # noqa: E402
import order_management_agent as agent  # noqa: E402


def _db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "courtbazaar")]


def _user(prefix):
    return {"user_id": f"test_oma_{prefix}_{uuid.uuid4().hex[:10]}"}


# Fakes of the OpenAI chat-completions API the agent calls
# — client.chat.completions.create(...) -> response.choices[0].message, with
# tool calls as message.tool_calls[i].function.{name, arguments (JSON str)}.
# The agent moved Gemini -> Groq -> OpenAI (see order_management_agent.py's
# provider note); Groq's API has the same shape, so the fakes are unchanged.
class _FakeCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, index, call):
        self.id = f"call_{index}"
        self.type = "function"
        self.function = _FakeFunction(call.name, json.dumps(call.args))


class _FakeMessage:
    def __init__(self, function_calls, text):
        self.content = text
        self.tool_calls = [_FakeToolCall(i, c) for i, c in enumerate(function_calls)] or None


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, function_calls=None, text=None):
        self.choices = [_FakeChoice(_FakeMessage(function_calls or [], text))]


class _FakeCompletions:
    def __init__(self, responses=None, delay=0, error=None):
        self._responses = list(responses or [])
        self._delay = delay
        self._error = error
        self.calls = []

    async def create(self, model, messages, tools, tool_choice):
        self.calls.append({"model": model, "messages": list(messages), "tools": tools, "tool_choice": tool_choice})
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._responses.pop(0)


class _FakeChat:
    def __init__(self, **kwargs):
        self.completions = _FakeCompletions(**kwargs)


class _FakeClient:
    def __init__(self, **kwargs):
        self.chat = _FakeChat(**kwargs)


def test_get_client_returns_none_without_api_key():
    original = os.environ.pop("OPENAI_API_KEY", None)
    try:
        assert agent._get_client() is None
    finally:
        if original is not None:
            os.environ["OPENAI_API_KEY"] = original


def test_summarize_all_without_api_key_degrades_gracefully():
    async def body():
        db = _db()
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            result = await agent.summarize_all(db)
            assert result["available"] is False
            assert result["reason"] == "OPENAI_API_KEY not configured"
            assert "hearings" in result and "escalated_hearings" in result and "open_flags" in result
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original
    asyncio.run(body())


def test_summarize_hearing_not_found_never_calls_model():
    async def body():
        db = _db()
        # No client injected and no API key needed — get_hearing_detail
        # returning None must short-circuit before any model call.
        result = await agent.summarize_hearing(db, "hearing_totally_missing")
        assert result == {"available": False, "reason": "Hearing not found", "hearing": None}
    asyncio.run(body())


def test_run_agent_executes_tool_call_then_returns_final_text():
    async def body():
        db = _db()
        fake_client = _FakeClient(responses=[
            _FakeResponse(function_calls=[_FakeCall("list_hearings", {})]),
            _FakeResponse(text="Everything looks fine."),
        ])
        result = await agent._run_agent(db, fake_client, "summarize everything")
        assert result == "Everything looks fine."
    asyncio.run(body())


def test_run_agent_stops_at_max_iterations():
    async def body():
        db = _db()
        # Every turn keeps requesting another tool call — never returns text —
        # so the loop must stop after max_iterations rather than looping forever.
        responses = [_FakeResponse(function_calls=[_FakeCall("list_hearings", {})]) for _ in range(10)]
        fake_client = _FakeClient(responses=responses)
        result = await agent._run_agent(db, fake_client, "summarize everything", max_iterations=3)
        assert "tool-call limit" in result
    asyncio.run(body())


def test_summarize_all_with_fake_client_flags_a_hearing():
    async def body():
        db = _db()
        hearing_id = f"hearing_omatest_{uuid.uuid4().hex[:10]}"
        try:
            fake_client = _FakeClient(responses=[
                _FakeResponse(function_calls=[_FakeCall(
                    "flag_for_admin_review",
                    {"hearing_id": hearing_id, "reason": "stalled", "agent_summary": "No movement in 5 days"},
                )]),
                _FakeResponse(text="Flagged one hearing for review."),
            ])
            result = await agent.summarize_all(db, client=fake_client)
            assert result["available"] is True
            assert result["summary"] == "Flagged one hearing for review."

            flag = await db.agent_review_flags.find_one({"hearing_id": hearing_id}, {"_id": 0})
            assert flag is not None
            assert flag["reason"] == "stalled"
        finally:
            await db.agent_review_flags.delete_many({"hearing_id": hearing_id})
    asyncio.run(body())


def test_summarize_all_times_out_gracefully():
    async def body():
        db = _db()
        original_timeout = agent.AGENT_TIMEOUT_SECONDS
        agent.AGENT_TIMEOUT_SECONDS = 0.05
        try:
            fake_client = _FakeClient(responses=[_FakeResponse(text="too slow")], delay=1.0)
            result = await agent.summarize_all(db, client=fake_client)
            assert result["available"] is False
            assert "timed out" in result["reason"]
            assert "hearings" in result  # fallback data still present
        finally:
            agent.AGENT_TIMEOUT_SECONDS = original_timeout
    asyncio.run(body())


def test_summarize_all_model_error_degrades_gracefully():
    async def body():
        db = _db()
        fake_client = _FakeClient(error=RuntimeError("upstream 500"))
        result = await agent.summarize_all(db, client=fake_client)
        assert result["available"] is False
        assert result["reason"] == "AI summary unavailable"
        assert "hearings" in result
    asyncio.run(body())


def test_execute_tool_dispatches_known_tools():
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]

            hearings_list = await agent._execute_tool(db, "list_hearings", {})
            assert any(h["hearing_id"] == hearing_id for h in hearings_list)

            escalated = await agent._execute_tool(db, "list_escalated_hearings", {})
            assert isinstance(escalated, list)

            detail = await agent._execute_tool(db, "get_hearing_detail", {"hearing_id": hearing_id})
            assert detail["hearing"]["hearing_id"] == hearing_id

            escrow_status = await agent._execute_tool(db, "get_escrow_status", {"hearing_id": hearing_id})
            assert escrow_status is None  # never paid in this test

            matching = await agent._execute_tool(db, "get_matching_session", {"hearing_id": hearing_id})
            assert matching is None  # never dispatched to matching in this test

            flagged = await agent._execute_tool(
                db, "flag_for_admin_review",
                {"hearing_id": hearing_id, "reason": "test", "agent_summary": "test summary"},
            )
            assert flagged["ok"] is True
        finally:
            if hearing_id:
                await db.hearing_requests.delete_many({"hearing_id": hearing_id})
                await db.agent_review_flags.delete_many({"hearing_id": hearing_id})
    asyncio.run(body())


def test_execute_tool_raises_on_unknown_tool():
    async def body():
        db = _db()
        try:
            await agent._execute_tool(db, "delete_everything", {})
            assert False, "expected ValueError"
        except ValueError as e:
            assert "Unknown tool" in str(e)
    asyncio.run(body())


def test_list_hearings_status_schema_accepts_null():
    """Regression for the Groq 400: 'parameters for tool list_hearings did
    not match schema: errors: [`/status`: expected string, but got null]'.
    The model sends an explicit `"status": null` (not an omitted key) when it
    has no filter to apply, so the declared type must include "null", not
    just leave `status` out of `required`."""
    declarations = agent._tool_declarations()
    list_hearings_decl = next(d for d in declarations if d["function"]["name"] == "list_hearings")
    status_schema = list_hearings_decl["function"]["parameters"]["properties"]["status"]
    assert status_schema["type"] == ["string", "null"] or (
        isinstance(status_schema["type"], list) and "null" in status_schema["type"]
    )


def test_execute_tool_list_hearings_with_null_status_arg():
    """End-to-end regression at the exact call shape _run_agent uses: Groq's
    tool-call JSON decodes `{"status": null}` to Python {"status": None} via
    json.loads, which _execute_tool then passes straight through to
    order_agent_tools.list_hearings — this must behave like no filter at all,
    not raise or silently return nothing."""
    async def body():
        db = _db()
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            result = await agent._execute_tool(db, "list_hearings", {"status": None})
            assert any(h["hearing_id"] == hearing_id for h in result)
        finally:
            if hearing_id:
                await db.hearing_requests.delete_many({"hearing_id": hearing_id})
    asyncio.run(body())


def test_tool_declarations_build_without_api_key():
    original = os.environ.pop("OPENAI_API_KEY", None)
    try:
        declarations = agent._tool_declarations()
        # OpenAI tool schema: one {"type": "function", "function": {...}} per tool.
        assert all(d["type"] == "function" and d["function"]["parameters"]["type"] == "object" for d in declarations)
        names = [d["function"]["name"] for d in declarations]
        assert len(names) == len(set(names))
        assert set(names) == {
            "get_attention_summary", "list_hearings", "list_escalated_hearings", "get_hearing_detail",
            "get_escrow_status", "get_matching_session", "flag_for_admin_review",
        }
    finally:
        if original is not None:
            os.environ["OPENAI_API_KEY"] = original


# --- OpenAI provider selection, model configuration, and key hygiene --------
FAKE_OPENAI_KEY = "sk-test-FAKEFAKEFAKE1234567890abcdef"


class _RecordingOpenAI(_FakeClient):
    """Stands in for openai.AsyncOpenAI so _get_client's own construction
    path runs without a real key or network."""
    instances = []
    completions_kwargs = {}

    def __init__(self, api_key=None, **kwargs):
        self.api_key = api_key
        _RecordingOpenAI.instances.append(self)
        super().__init__(**_RecordingOpenAI.completions_kwargs)


def _patch_openai(monkeypatch, **completions_kwargs):
    import openai
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI_KEY)
    _RecordingOpenAI.instances = []
    _RecordingOpenAI.completions_kwargs = completions_kwargs
    monkeypatch.setattr(openai, "AsyncOpenAI", _RecordingOpenAI)


def test_get_client_selects_openai_not_groq(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI_KEY)
    # A Groq key being present as well must not change the provider.
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_should_be_ignored")
    import openai
    client = agent._get_client()
    assert isinstance(client, openai.AsyncOpenAI)
    assert client.api_key == FAKE_OPENAI_KEY
    assert "api.openai.com" in str(client.base_url)


def test_get_client_ignores_groq_key_when_openai_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_should_be_ignored")
    assert agent._get_client() is None


def test_model_defaults_to_gpt_4o_mini_and_honours_openai_model(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert agent._get_model() == "gpt-4o-mini"
    monkeypatch.setenv("OPENAI_MODEL", "  ")
    assert agent._get_model() == "gpt-4o-mini"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    assert agent._get_model() == "gpt-4o"


def test_summarize_all_uses_openai_client_and_configured_model(monkeypatch):
    """No client injected — exactly the path the admin route takes."""
    async def body():
        db = _db()
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
        _patch_openai(monkeypatch, responses=[
            _FakeResponse(function_calls=[_FakeCall("get_attention_summary", {})]),
            _FakeResponse(text="Nothing needs attention."),
        ])

        result = await agent.summarize_all(db)

        assert result["available"] is True
        assert result["summary"] == "Nothing needs attention."
        assert "hearings" in result and "escalated_hearings" in result and "open_flags" in result
        assert len(_RecordingOpenAI.instances) == 1
        client = _RecordingOpenAI.instances[0]
        assert client.api_key == FAKE_OPENAI_KEY
        calls = client.chat.completions.calls
        assert len(calls) == 2
        assert all(c["model"] == "gpt-4o-mini" for c in calls)
        assert calls[0]["messages"][0] == {"role": "system", "content": agent.SYSTEM_PROMPT}
        assert FAKE_OPENAI_KEY not in json.dumps(result, default=str)
    asyncio.run(body())


def test_summarize_hearing_without_api_key_is_safe(monkeypatch):
    async def body():
        db = _db()
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        requester = _user("requester")
        hearing_id = None
        try:
            hearing = await hearings.create_hearing_request(
                db, requester["user_id"], "court_tishazari", "2026-09-01", "Test case", 1000.0, None,
            )
            hearing_id = hearing["hearing_id"]
            result = await agent.summarize_hearing(db, hearing_id)
            assert result["available"] is False
            assert result["reason"] == "OPENAI_API_KEY not configured"
            assert "summary" not in result
            assert result["hearing"]["hearing_id"] == hearing_id
        finally:
            if hearing_id:
                await db.hearing_requests.delete_many({"hearing_id": hearing_id})
    asyncio.run(body())


def test_openai_failure_is_safe_and_never_leaks_the_key(monkeypatch, caplog):
    """An upstream auth error can echo the key back in its message; neither
    the response nor the server log may carry it."""
    async def body():
        db = _db()
        _patch_openai(monkeypatch, error=RuntimeError(
            f"Error code: 401 - Incorrect API key provided: {FAKE_OPENAI_KEY}. "
            "Also seen: Bearer sk-proj-anotherSecretLookingValue123"
        ))

        with caplog.at_level("DEBUG"):
            result = await agent.summarize_all(db)

        assert result["available"] is False
        assert result["reason"] == "AI summary unavailable"
        assert "summary" not in result
        assert "hearings" in result  # fallback data still present
        assert len(_RecordingOpenAI.instances[0].chat.completions.calls) == 1

        serialized = json.dumps(result, default=str)
        assert "Order Management Agent failed (RuntimeError)" in caplog.text
        for secret in (FAKE_OPENAI_KEY, "sk-proj-anotherSecretLookingValue123", "sk-"):
            assert secret not in serialized
            assert secret not in caplog.text
    asyncio.run(body())


def test_success_path_never_logs_or_returns_the_key(monkeypatch, caplog):
    async def body():
        db = _db()
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        _patch_openai(monkeypatch, responses=[_FakeResponse(text="All clear.")])
        with caplog.at_level("DEBUG"):
            result = await agent.summarize_all(db)
        assert result["available"] is True
        assert "provider=openai requested_model=gpt-4o-mini" in caplog.text
        assert FAKE_OPENAI_KEY not in caplog.text
        assert FAKE_OPENAI_KEY not in json.dumps(result, default=str)
    asyncio.run(body())
