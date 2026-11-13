"""rag_provisions.expand_chunks: a keyword hit on a bare rule heading (2026-11-05).

"Who pays the advance on costs in DIAC arbitration?" was answered from Rule
33.2 only. BM25 matched "33. Advance on Costs" (the heading, no text of its
own) and the table-of-contents line "33 Advance on Costs 28"; the chunk that
held Rule 33.1 (the 50/50 split) came after enough other chunks that
MAX_BLOCKS cut it. A heading hit now brings its sub-rules; a TOC line is dropped.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rag_provisions  # noqa: E402

FILLER = [f"{n}. Filler rule {n}\nThis filler provision number {n} talks about procedural matter {n} in some detail." for n in range(1, 21)]
DOC = "\n".join([
    "CONTENTS",
    "33 Advance on Costs 28",
    "ARBITRATION PROCEEDINGS RULES",
    *FILLER,
    "33. Advance on Costs",
    "33.1 Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant and the remaining 50% by the Respondent.",
    "33.2 Parties are jointly and severally liable for the deposits as directed by the Centre.",
])
CHUNKS = [f.split("\n")[1] for f in FILLER[:15]]  # enough retrieved chunks to fill MAX_BLOCKS on their own


def test_heading_hit_brings_its_sub_rules_past_the_block_cap():
    blocks = rag_provisions.expand_chunks("DIAC.pdf", CHUNKS, DOC, "Who pays the advance on costs?")
    text = "\n".join(blocks)
    assert "| Rule 33.1" in text and "50% of such deposits" in text
    assert "Advance on Costs 28" not in text  # the table-of-contents line never takes a slot


def test_with_rule_body_keeps_ordinary_hits_and_drops_toc_lines():
    provisions = rag_provisions.parse_provisions(DOC)
    index = {(p["instrument"], p["number"]): i for i, p in enumerate(provisions)}
    toc, head, sub = index[(0, "33")], index[(1, "33")], index[(1, "33.2")]
    assert rag_provisions._with_rule_body(provisions, [toc]) == []
    assert rag_provisions._with_rule_body(provisions, [sub]) == [sub]
    assert rag_provisions._with_rule_body(provisions, [head]) == [head, index[(1, "33.1")], sub]
