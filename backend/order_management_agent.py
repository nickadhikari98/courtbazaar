"""Order Management Agent — Groq (Llama 3.3 70B) orchestration.

Read-first, human-in-the-loop reasoning layer over the existing
hearing_requests order book (see order_agent_tools.py for the tool layer).
This module NEVER calls a state-changing hearings.py/escrow.py/
counsel_matching.py function — its only write path is
order_agent_tools.flag_for_admin_review, which lands in the new, additive
agent_review_flags collection.

Deliberately stateless between invocations: every call re-fetches current DB
state through the tool layer.

GROQ_API_KEY is a new, optional env var; if it isn't set, or the model call
times out/errors, every public function here degrades to a plain "AI
summary unavailable" response carrying the raw tool data underneath, never
a 500.

Provider note: originally built against Gemini 2.5 Flash per the approved
spec. Switched to Groq (Llama 3.3 70B) because Gemini 2.5 Flash was
deprecated for new API keys by Google. Groq's API is OpenAI-compatible
(chat completions + tools), so the request/response shape here differs from
the earlier Gemini version, but the tool set, system prompt intent, and all
read-only/write boundaries are unchanged.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import order_agent_tools

logger = logging.getLogger(__name__)

GROQ_MODEL = "openai/gpt-oss-120b"
AGENT_TIMEOUT_SECONDS = 25
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are the Order Management Agent for CourtBazaar, a legal-services marketplace.
You assist Admin/Founder users by reasoning over hearing-request order data that is
already tracked correctly by the platform's backend. You never invent facts — every
claim you make must trace to data returned by your tools.

You have READ-ONLY tools: get_attention_summary, list_hearings, list_escalated_hearings,
get_hearing_detail, get_escrow_status, get_matching_session. You have exactly one write
tool, flag_for_admin_review, which only records that a hearing needs human attention —
it does not change the hearing's status, money, or assignment in any way.

You must NEVER:
- Claim a payment, payout, verification, or assignment has happened unless the tool
  data explicitly shows it.
- Recommend an action as if it were already taken.
- Attempt to call any tool other than the seven listed above.
- Fabricate a hearing_id, user_id, court name, or amount not present in tool output.

For each hearing you discuss, ground your summary in: current status, how long it has
been in that status (using timestamps returned by the tools), whether it is within a
known deterministic deadline (order-sheet reminder at 3 days, auto-release at 3 days,
admin grace period at 24 hours from escalation — these deadlines are enforced by
existing scheduled jobs, not by you), and whose turn it is to act next.

For a PLATFORM-WIDE summary, call get_attention_summary first — it already returns
total/by-status counts plus only the hearings that meet a genuine risk rule, each with
why it was flagged (risk_reasons). Only call list_hearings if you genuinely need the
complete unfiltered list for some other reason — it returns every hearing and is far
larger. Rank the candidates get_attention_summary gives you by genuine risk: closest to
an automatic deadline, escalated with no admin action yet, or stalled with no recent
timeline activity — not by raw age alone. Only call get_hearing_detail/get_escrow_status/
get_matching_session for a specific candidate when its risk_reasons and triage fields
genuinely aren't enough to write a clear summary and recommendation for it — most
candidates won't need that.

When you believe a hearing needs a human to look at it, call flag_for_admin_review
with a concise reason and summary. Do not flag hearings that are progressing normally
or are in a terminal state (completed, rated, cancelled, rejected, expired).

If tool data is missing, incomplete, or contradictory, say so plainly rather than
guessing. You are a summarization and triage aid, not a decision-maker — the human
reading your output makes every final call.

Respond with your final answer as plain text — a concise, readable summary. Call
tools as needed before answering; do not answer before you have fetched the data you
need."""


def _tool_declarations() -> List[Dict[str, Any]]:
    """OpenAI/Groq-style tool schema (list of {"type": "function", "function": {...}})."""
    hearing_id_prop = {"type": "string", "description": "The hearing_id to look up"}
    return [
        {
            "type": "function",
            "function": {
                "name": "get_attention_summary",
                "description": (
                    "Platform-wide triage in one call: total hearing count, counts by status, and "
                    "a short list of only the hearings that meet a genuine risk criterion (disputed, "
                    "verification nearing/past the 3-day auto-release deadline, order sheet overdue, "
                    "payment stalled, verified but payout not yet released, escalated with no counsel "
                    "assigned, or stalled with no recent activity), each with minimal triage fields "
                    "and why it was flagged (risk_reasons). Call this FIRST for any platform-wide "
                    "summary instead of list_hearings — it is far smaller and already does the risk "
                    "filtering, while total/by_status still covers every hearing."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_hearings",
                "description": "List hearing requests, optionally filtered by status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        # Nullable (not just optional) — Groq's tool-call validator rejects an
                        # explicit `"status": null` (which the model sends when it has no filter
                        # to apply) against a bare {"type": "string"} schema, even though the key
                        # is already outside `required`. See order_management_agent's tests for
                        # the regression this covers.
                        "status": {"type": ["string", "null"], "description": "Status filter, e.g. 'verification_pending'. Omit the field or pass null for no filter (all hearings)."},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_escalated_hearings",
                "description": "List hearings whose counsel-matching session was escalated to admin with no assignment yet.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_hearing_detail",
                "description": "Get the full record and uploaded documents for one hearing.",
                "parameters": {"type": "object", "properties": {"hearing_id": hearing_id_prop}, "required": ["hearing_id"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_escrow_status",
                "description": "Get the escrow/payment record for one hearing.",
                "parameters": {"type": "object", "properties": {"hearing_id": hearing_id_prop}, "required": ["hearing_id"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_matching_session",
                "description": "Get the counsel-matching session (tiers, escalation reason) for one hearing.",
                "parameters": {"type": "object", "properties": {"hearing_id": hearing_id_prop}, "required": ["hearing_id"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flag_for_admin_review",
                "description": "Record that a hearing needs human review. Does not change the hearing itself.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hearing_id": hearing_id_prop,
                        "reason": {"type": "string", "description": "Short machine-readable reason"},
                        "agent_summary": {"type": "string", "description": "Human-readable explanation"},
                    },
                    "required": ["hearing_id", "reason", "agent_summary"],
                },
            },
        },
    ]


async def _execute_tool(db, name: str, args: Dict[str, Any]) -> Any:
    if name == "get_attention_summary":
        return await order_agent_tools.get_attention_summary(db)
    if name == "list_hearings":
        return await order_agent_tools.list_hearings(db, args.get("status"))
    if name == "list_escalated_hearings":
        return await order_agent_tools.list_escalated_hearings(db)
    if name == "get_hearing_detail":
        return await order_agent_tools.get_hearing_detail(db, args["hearing_id"])
    if name == "get_escrow_status":
        return await order_agent_tools.get_escrow_status(db, args["hearing_id"])
    if name == "get_matching_session":
        return await order_agent_tools.get_matching_session(db, args["hearing_id"])
    if name == "flag_for_admin_review":
        return await order_agent_tools.flag_for_admin_review(
            db, args["hearing_id"], args["reason"], args["agent_summary"],
        )
    raise ValueError(f"Unknown tool: {name}")


def _get_client():
    """Returns an AsyncGroq client, or None if GROQ_API_KEY isn't configured —
    the one degrade-gracefully branch every caller below must handle. Reads
    the env var lazily (not at import time) so importing this module never
    requires the key."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    from groq import AsyncGroq
    return AsyncGroq(api_key=api_key)


async def _run_agent(db, client, user_prompt: str,
                      max_iterations: int = MAX_TOOL_ITERATIONS) -> str:
    """Bounded tool-calling loop using Groq's OpenAI-compatible chat completions API."""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    tools = _tool_declarations()

    for _ in range(max_iterations):
        response = await client.chat.completions.create(
            model=GROQ_MODEL, messages=messages, tools=tools, tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return message.content or ""

        # Echo the assistant's tool-call message back exactly (required for
        # the follow-up "tool" role messages to be valid in the next turn).
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = await _execute_tool(db, tc.function.name, args)
            except Exception as e:
                result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    return "Reached the tool-call limit before producing a final summary — please retry or narrow the request."


async def _run_with_fallback(db, user_prompt: str, fallback_data: Dict[str, Any],
                              client=None) -> Dict[str, Any]:
    """Shared timeout/error envelope for both public entry points below."""
    resolved_client = client if client is not None else _get_client()
    if resolved_client is None:
        return {"available": False, "reason": "GROQ_API_KEY not configured", **fallback_data}
    try:
        text = await asyncio.wait_for(
            _run_agent(db, resolved_client, user_prompt), timeout=AGENT_TIMEOUT_SECONDS,
        )
        return {"available": True, "summary": text, **fallback_data}
    except asyncio.TimeoutError:
        logger.error("Order Management Agent timed out after %ss", AGENT_TIMEOUT_SECONDS)
        return {"available": False, "reason": "AI summary unavailable — request timed out", **fallback_data}
    except Exception as e:
        logger.error("Order Management Agent failed: %s", e)
        return {"available": False, "reason": "AI summary unavailable", **fallback_data}


async def summarize_all(db, client=None) -> Dict[str, Any]:
    hearings = await order_agent_tools.list_hearings(db)
    escalated = await order_agent_tools.list_escalated_hearings(db)
    open_flags = await order_agent_tools.list_open_flags(db)
    fallback_data = {"hearings": hearings, "escalated_hearings": escalated, "open_flags": open_flags}
    prompt = (
        "Give a platform-wide summary of hearings that need attention right now, ranked by "
        "genuine risk. Call get_attention_summary first — it already covers every hearing (total "
        "and by-status counts) and returns only the pre-filtered risk candidates, each with why it "
        "was flagged. Use get_hearing_detail/get_escrow_status/get_matching_session only for a "
        "candidate whose risk_reasons and triage fields aren't enough on their own to summarize. "
        "Flag any hearing that genuinely needs a human to look at it via flag_for_admin_review."
    )
    return await _run_with_fallback(db, prompt, fallback_data, client=client)


async def summarize_hearing(db, hearing_id: str, client=None) -> Dict[str, Any]:
    detail = await order_agent_tools.get_hearing_detail(db, hearing_id)
    if detail is None:
        return {"available": False, "reason": "Hearing not found", "hearing": None}
    escrow = await order_agent_tools.get_escrow_status(db, hearing_id)
    matching = await order_agent_tools.get_matching_session(db, hearing_id)
    fallback_data = {"hearing": detail["hearing"], "documents": detail["documents"],
                      "escrow": escrow, "matching_session": matching}
    prompt = (
        f"Summarize the current state of hearing {hearing_id} in plain language, and "
        "recommend a next action if one is needed. Use get_hearing_detail, get_escrow_status, "
        "and get_matching_session to ground your answer. Call flag_for_admin_review only if "
        "this hearing genuinely needs human attention right now."
    )
    return await _run_with_fallback(db, prompt, fallback_data, client=client)
