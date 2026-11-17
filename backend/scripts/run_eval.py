"""Arbitration knowledge-base evaluation (not part of pytest; costs API calls).

Runs each question in tests/eval/arbitration_eval.jsonl through the real
answer pipeline (ai_chat.route_message -> prompt_builder -> llm_service.
generate_response, as ai_chat does for a document question) and prints, per
expected source: questions, right-document rate, right-provision rate and
wrong-institution count, plus the average total tokens per question (every
model call summed). Any answer citing a superseded document is a FAILURE.

    cd backend && python scripts/run_eval.py [--limit N] [--mode layman|lawyer]
"""
import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from openai.resources.chat.completions import AsyncCompletions  # noqa: E402
from openai.resources.responses import AsyncResponses  # noqa: E402

import ai_chat  # noqa: E402
import kb_registry  # noqa: E402
import llm_service  # noqa: E402
import prompt_builder  # noqa: E402

EVAL_FILE = ROOT / "tests" / "eval" / "arbitration_eval.jsonl"
_tokens = [0]


def _count_tokens(create):
    async def wrapped(self, *args, **kwargs):
        result = await create(self, *args, **kwargs)
        usage = getattr(result, "usage", None)
        _tokens[0] += getattr(usage, "total_tokens", 0) or 0
        return result
    return wrapped


# Every model call goes through one of these two, whichever client made it.
AsyncResponses.create = _count_tokens(AsyncResponses.create)
AsyncCompletions.create = _count_tokens(AsyncCompletions.create)

RECORDS = {r["doc_id"]: (f, r) for f in kb_registry.approved_files()
           for r in kb_registry.records_for_file(f) or []}
SUPERSEDED = {d for d, (_, r) in RECORDS.items() if r.get("status") == "superseded"}


def cited_docs(citation, sources):
    """doc_ids a citation stands for: the rule set its title names, else
    every record of the answered files whose display label it carries."""
    title = citation.get("title") or ""
    recs = [(d, f, r) for d, (f, r) in RECORDS.items() if f in sources]
    named = [d for d, f, r in recs if title.startswith(kb_registry.rule_set_title(r))]
    return named or [d for d, f, r in recs if kb_registry.display_label(f) in (title, citation.get("document"))]


def provision_hit(expected, citations_for_doc):
    """"Rule 8.6" / "Appendix IV, Article 7": the number is cited, as itself, a
    sub-provision of it, or its parent (a citation of "9" for "9.8")."""
    m = re.match(r"(?:(Appendix [IVX]+), )?(?:Rule|Article|Section) (\S+)$", expected)
    appendix, number = m.group(1), m.group(2)
    for c in citations_for_doc:
        if appendix and not (c.get("label") or "").startswith(appendix):
            continue
        if not appendix and (c.get("label") or "").startswith("Appendix"):
            continue
        for r in c.get("rule_labels") or c.get("rules") or []:
            r = r.split("(")[0]
            if r == number or r.startswith(number + ".") or number.startswith(r + "."):
                return True
    return False


async def ask(question, mode):
    decision = ai_chat.route_message(question)
    use_rag = decision["route"] in ai_chat.RAG_ROUTES
    messages = [{"role": "system", "content": ai_chat.SYSTEM_PROMPT}, {"role": "user", "content": question}]
    if use_rag and decision["route"] == ai_chat.ROUTE_DOCUMENT_RAG and decision["source"] != llm_service.SOURCE_SOP:
        messages = prompt_builder.build_legal_system_messages(
            prompt_builder.subject_for(decision["source"]), mode, prompt_builder.detect_intent(question)) + messages[1:]
    result = await llm_service.generate_response(
        messages, use_file_search=use_rag, selected_source=decision["source"] if use_rag else None)
    return result if result.get("ok") else {**result, "citations": [], "sources": []}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--mode", default="layman", choices=("layman", "lawyer"))
    args = parser.parse_args()
    cases = [json.loads(line) for line in EVAL_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = cases[:args.limit] if args.limit else cases
    stats = defaultdict(lambda: {"n": 0, "doc": 0, "prov": 0, "wrong_inst": 0})
    failures, per_question_tokens = [], []
    for case in cases:
        _tokens[0] = 0
        try:
            result = await ask(case["question"], args.mode)
        except Exception as e:  # one broken question must not hide the rest
            result = {"citations": [], "sources": [], "error": f"{type(e).__name__}: {e}"}
        per_question_tokens.append(_tokens[0])
        citations = [c for c in result.get("citations") or [] if c.get("kind", "document") == "document"]
        sources = result.get("sources") or []
        docs = {d for c in citations for d in cited_docs(c, sources)}
        for f in sources:  # a superseded file answering at all is a failure, cited rule or not
            docs |= {d for d, (rf, _) in RECORDS.items() if rf == f and d in SUPERSEDED}
        for d in sorted(docs & SUPERSEDED):
            failures.append(f"FAILURE superseded {d} cited for: {case['question']}")
        expected = case["expected_doc_id"]
        expected = [expected] if isinstance(expected, str) else (expected or [])
        key = "cross-institution" if len(expected) > 1 else (expected[0] if expected else "not in KB")
        row = stats[key]
        row["n"] += 1
        if not case["should_answer"]:
            # Right = declined: no document citation with a rule.
            declined = not any(c.get("rules") for c in citations)
            row["doc"] += declined
            row["prov"] += declined
            row["wrong_inst"] += bool(docs)
            continue
        provisions = case["expected_provision"]
        provisions = [provisions] if isinstance(provisions, str) else provisions
        row["doc"] += set(expected) <= docs
        row["prov"] += all(provision_hit(p, [c for c in citations if d in cited_docs(c, sources)])
                           for d, p in zip(expected, provisions))
        codes = {kb_registry.record_code(RECORDS[d][1]) for d in expected}
        row["wrong_inst"] += sum(kb_registry.record_code(RECORDS[d][1]) not in codes for d in docs if d in RECORDS)
        if result.get("error"):
            print(f"ERROR {result['error']} for: {case['question']}")

    print(f"\n{'source':32} {'qs':>3} {'right doc':>10} {'right prov':>11} {'wrong inst':>11}")
    total = {"n": 0, "doc": 0, "prov": 0, "wrong_inst": 0}
    for key in sorted(stats):
        row = stats[key]
        for k in total:
            total[k] += row[k]
        print(f"{key:32} {row['n']:>3} {row['doc'] / row['n']:>10.0%} {row['prov'] / row['n']:>11.0%} {row['wrong_inst']:>11}")
    print(f"{'TOTAL':32} {total['n']:>3} {total['doc'] / total['n']:>10.0%} "
          f"{total['prov'] / total['n']:>11.0%} {total['wrong_inst']:>11}")
    print(f"\nAverage total tokens per question: {sum(per_question_tokens) / len(per_question_tokens):,.0f}")
    for line in failures:
        print(line)
    if not failures:
        print("Superseded-document check: no superseded document cited.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
