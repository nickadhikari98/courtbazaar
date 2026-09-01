"""Order Management Agent — orchestration (order_management_agent.py).
Exercises the degrade-gracefully paths (no API key / timeout / model error)
and the tool-calling loop against a fake client, so these tests need no real
Gemini API key or network access — same "best-effort, never propagate"
convention as hearings.check_pending_order_sheets/auto_release_stale_
verifications. The tool-dispatch test and the "hearing not found" test run
against a real local MongoDB (same conventions as the other test files).
"""
import asyncio
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


class _FakeCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _FakeResponse:
    def __init__(self, function_calls=None, text=None):
        self.function_calls = function_calls or []
        self.text = text


class _FakeModels:
    def __init__(self, responses=None, delay=0, error=None):
        self._responses = list(responses or [])
        self._delay = delay
        self._error = error

    async def generate_content(self, model, contents, config):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._responses.pop(0)


class _FakeAio:
    def __init__(self, **kwargs):
        self.models = _FakeModels(**kwargs)


class _FakeClient:
    def __init__(self, **kwargs):
        self.aio = _FakeAio(**kwargs)


def test_get_client_returns_none_without_api_key():
    original = os.environ.pop("GEMINI_API_KEY", None)
    try:
        assert agent._get_client() is None
    finally:
        if original is not None:
            os.environ["GEMINI_API_KEY"] = original


def test_summarize_all_without_api_key_degrades_gracefully():
    async def body():
        db = _db()
        original = os.environ.pop("GEMINI_API_KEY", None)
        try:
            result = await agent.summarize_all(db)
            assert result["available"] is False
            assert result["reason"] == "GEMINI_API_KEY not configured"
            assert "hearings" in result and "escalated_hearings" in result and "open_flags" in result
        finally:
            if original is not None:
                os.environ["GEMINI_API_KEY"] = original
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
    original = os.environ.pop("GEMINI_API_KEY", None)
    try:
        declarations = agent._tool_declarations()
        assert len(declarations) == 1
        names = {fd.name for fd in declarations[0].function_declarations}
        assert names == {
            "list_hearings", "list_escalated_hearings", "get_hearing_detail",
            "get_escrow_status", "get_matching_session", "flag_for_admin_review",
        }
    finally:
        if original is not None:
            os.environ["GEMINI_API_KEY"] = original
