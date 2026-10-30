"""answer_guard: no misleading fragments after unsupported text is removed (2026-10-16).

Seen on dev for "explain the advance on costs using headings, numbered steps,
nested bullets and separators" against the DIAC Rules:

- "The fees, costs." — _supported_prefix cut "The fees, costs, and expenses
  ... must be paid entirely in advance (Rule 4(ii))." back to its leading
  supported clauses, which were only a list of nouns with no verb.
- "### 6." — _lines split the heading "### 6. Non-Refundable Costs" into the
  sentences "6." and "Non-Refundable Costs"; the second was unsupported and
  dropped, the bare number stayed, so _rebuild never saw an empty heading.

Removal itself is unchanged: an unsupported claim is still dropped and still
counts toward the "too much unsupported -> fallback" rule, and nothing is ever
added back. These tests pin that a removal can't leave a fragment behind.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import answer_guard  # noqa: E402

EVIDENCE = """Rule 4 Advance payment
4. The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.
5. Miscellaneous expenses shall be determined by the Coordinator and shall be paid equally by the parties.
6. The Coordinator shall maintain an account of the Administrative Costs and miscellaneous expenses.
33.5 If a party fails to make the deposits as directed within thirty days from the date on which it is due, the Centre may terminate the arbitration."""

PARTIAL = answer_guard.PARTIAL_ANSWER_NOTE


def _validate(answer):
    return answer_guard.validate_grounded_answer(answer, EVIDENCE, document_evidence=True)


# --- truncated sentences ----------------------------------------------------

def test_a_cut_that_leaves_only_a_list_of_nouns_drops_the_sentence():
    answer = ("The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties (Rule 4).\n"
              "The fees, costs, and expenses determined by the Treasury must be refunded within 90 days.")
    result = _validate(answer)
    assert result is not None
    assert "The fees, costs." not in result
    assert "The fees" not in result
    assert "shared equally by the parties (Rule 4)." in result
    assert result.endswith(PARTIAL)


def test_a_cut_that_leaves_a_complete_clause_is_still_kept():
    answer = ("Miscellaneous expenses shall be determined by the Coordinator, and the Coordinator shall "
              "refund them within 90 days.")
    result = _validate(answer)
    assert result.startswith("Miscellaneous expenses shall be determined by the Coordinator.")
    assert "90 days" not in result and "refund" not in result.split("\n\n")[0]


# --- empty headings and list items -----------------------------------------

def test_a_numbered_heading_whose_title_is_dropped_goes_with_its_section():
    answer = ("### 1. Sharing of costs\n"
              "- The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.\n"
              "- Miscellaneous expenses shall be paid equally by the parties.\n"
              "- The Coordinator shall maintain an account of the Administrative Costs.\n\n"
              "### 6. Non-Refundable Costs\n"
              "- Administrative Costs.")
    result = _validate(answer)
    assert result is not None
    assert "### 6." not in result
    assert "Non-Refundable" not in result
    # Written under the unsupported heading, so it goes with it instead of
    # reading as a fourth point of section 1.
    assert "- Administrative Costs." not in result
    assert result.startswith("### 1. Sharing of costs\n- The Administrative Costs")
    assert result.endswith(PARTIAL)


def test_a_full_statement_under_a_dropped_heading_stays_separate_from_the_section_above():
    answer = ("## Sharing\n"
              "- The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.\n"
              "- Miscellaneous expenses shall be paid equally by the parties.\n"
              "## Fees waived for claimants\n"
              "- The Coordinator shall maintain an account of the Administrative Costs.")
    result = _validate(answer)
    assert "waived" not in result
    assert ("- Miscellaneous expenses shall be paid equally by the parties.\n\n"
            "- The Coordinator shall maintain an account") in result


def test_when_the_dropped_section_outweighs_what_is_left_the_answer_falls_back():
    answer = ("### 1. Sharing of costs\n"
              "- The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.\n\n"
              "### 6. Non-Refundable Costs\n"
              "- Administrative Costs.")
    assert _validate(answer) is None


def test_a_supported_numbered_heading_keeps_its_number():
    answer = ("### 2. Miscellaneous expenses\n"
              "- Miscellaneous expenses shall be paid equally by the parties (Rule 5).")
    assert _validate(answer) == answer


def test_a_bullet_reduced_to_nothing_leaves_no_empty_marker():
    answer = ("- The Coordinator shall maintain an account of the Administrative Costs.\n"
              "- 500 rupees are payable by the Treasury.\n"
              "- Miscellaneous expenses shall be paid equally by the parties.")
    result = _validate(answer)
    lines = result.split("\n\n")[0].splitlines()
    assert lines == ["- The Coordinator shall maintain an account of the Administrative Costs.",
                     "- Miscellaneous expenses shall be paid equally by the parties."]


def test_separators_never_frame_an_empty_section_or_dangle_at_the_end():
    answer = ("## Sharing\n"
              "The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.\n\n"
              "---\n\n"
              "## Refunds\n"
              "All fees are refundable by the Treasury within 90 days.\n\n"
              "---\n\n"
              "## Expenses\n"
              "Miscellaneous expenses shall be paid equally by the parties.\n\n"
              "---")
    result = _validate(answer)
    body = result.split("\n\n" + PARTIAL)[0]
    assert "Refunds" not in body
    assert body.count("---") == 1  # one between the two surviving sections
    assert not body.rstrip().endswith("---")
    assert "---\n\n---" not in body


def test_separators_alone_never_count_as_an_answer():
    assert _validate("---\n\n## Refunds\nAll fees are refundable by the Treasury within 90 days.\n\n---") is None


# --- valid structured answers and citations are untouched --------------------

def test_a_fully_supported_structured_answer_is_returned_unchanged():
    answer = ("If a party fails to pay, the Centre may terminate the arbitration (Rule 33.5).\n\n"
              "## Sharing\n"
              "1. The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties (Rule 4).\n"
              "2. Miscellaneous expenses shall be paid equally by the parties (Rule 5).\n\n"
              "---\n\n"
              "## Accounts\n"
              "- The Coordinator shall maintain an account of the Administrative Costs (Rule 6).")
    assert _validate(answer) == answer


# --- unsupported claims ------------------------------------------------------

def test_mostly_unsupported_answers_still_fall_back():
    answer = ("The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.\n"
              "The Treasury refunds all fees within 90 days.\n"
              "An appeal lies to the Supreme Court within 30 days.")
    assert _validate(answer) is None


def test_nothing_unsupported_is_rebuilt_or_given_a_rule_number():
    answer = ("### 3. Refunds\n"
              "- All fees are refundable by the Treasury within 90 days (Rule 9).\n\n"
              "### 4. Sharing\n"
              "- The Administrative Costs and the Arbitrators' fees shall be shared equally by the parties.")
    result = _validate(answer)
    assert "Rule 9" not in result and "refundable" not in result and "### 3." not in result
    assert "(Rule" not in result.split("\n\n")[0]  # no rule number was added to the kept sentence


def test_general_answers_get_the_same_heading_cleanup():
    answer = ("### 1. What it is\nAnticipatory bail is bail sought before arrest.\n\n"
              "### 2. Leading case\nArnesh Kumar v. State of Bihar decided this.")
    result = answer_guard.guard_general_answer(answer, legal=True)
    assert "### 2." not in result and "Arnesh" not in result
    assert result.startswith("### 1. What it is\nAnticipatory bail is bail sought before arrest.")


# --- the rule's own word for who it applies to -------------------------------
# Rule 33.5 says "a party"; an answer to "what if the claimant doesn't pay"
# wrote "the claimant", narrowing a rule that applies to every party.

RULE_33 = {
    "33.1": "33.1 Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant and "
            "the remaining 50% of such deposits shall be payable by the Respondent.",
    "33.5": "33.5 If a party fails to make the deposits as directed within thirty days from the date on which it "
            "is due, the Centre may terminate the arbitration. This shall however be without prejudice to the "
            "party reintroducing the same Claims in another proceeding, in accordance with law.",
}


def test_a_party_rule_narrowed_to_the_claimant_is_restored_to_the_rules_wording():
    answer = ("If the Claimant fails to make the deposits within thirty days, the Centre may terminate the "
              "arbitration (Rule 33.5).")
    result, dropped = answer_guard.validate_rule_attribution(answer, RULE_33)
    assert dropped == 0
    assert result == ("If a party (including the Claimant) fails to make the deposits within thirty days, "
                      "the Centre may terminate the arbitration (Rule 33.5).")


def test_a_sentence_opening_with_the_claimant_is_restored_with_a_capital():
    answer = ("The Claimant that fails to make the deposits within thirty days faces termination: the Centre may "
              "terminate the arbitration (Rule 33.5).")
    result, dropped = answer_guard.validate_rule_attribution(answer, RULE_33)
    assert dropped == 0
    assert result.startswith("A party (including the Claimant) that fails to make the deposits")


def test_a_narrowed_sentence_that_fails_other_checks_is_never_rescued_by_the_rewrite():
    # "The Claimant may reintroduce": the rule gives no actor that power in
    # those words, so it fails on its own; adding "a party" must not save it.
    answer = ("If a party fails to make the deposits within thirty days, the Centre may terminate the arbitration "
              "(Rule 33.5).\n"
              "The Claimant may reintroduce the same Claims in another proceeding, in accordance with law (Rule 33.5).")
    result, dropped = answer_guard.validate_rule_attribution(answer, RULE_33)
    assert dropped == 1 and "reintroduce" not in result


def test_a_narrowed_sentence_that_still_fails_once_restored_is_dropped():
    # Restoring "a party" doesn't fix the wrong actor (the Tribunal never terminates under 33.5 here).
    answer = ("If a party fails to make the deposits within thirty days, the Centre may terminate the arbitration "
              "(Rule 33.5).\n"
              "If the Claimant fails to make the deposits within thirty days, the Tribunal may refund the "
              "deposits (Rule 33.5).")
    result, dropped = answer_guard.validate_rule_attribution(answer, RULE_33)
    assert dropped == 1
    assert "Tribunal" not in result and "including the Claimant" not in result


def test_a_possessive_narrowing_is_not_rewritten_and_is_dropped():
    answer = ("If a party fails to make the deposits within thirty days, the Centre may terminate the arbitration "
              "(Rule 33.5).\n"
              "This is without prejudice to the Claimant's right to reintroduce the same Claims (Rule 33.5).")
    result, dropped = answer_guard.validate_rule_attribution(answer, RULE_33)
    assert dropped == 1 and "Claimant's" not in result


def test_naming_who_a_party_includes_keeps_the_rule_wording():
    answer = ("If a party (including the Claimant) fails to make the deposits within thirty days, the Centre may "
              "terminate the arbitration (Rule 33.5).")
    assert answer_guard.validate_rule_attribution(answer, RULE_33) == (answer, 0)


def test_a_rule_that_names_the_claimant_may_be_stated_for_the_claimant():
    answer = "Unless the Centre directs otherwise, 50% of such deposits shall be payable by the Claimant (Rule 33.1)."
    assert answer_guard.validate_rule_attribution(answer, RULE_33) == (answer, 0)


def test_document_answer_instructions_require_the_rules_own_party_wording():
    import llm_service
    text = llm_service.RAG_EVIDENCE_INSTRUCTIONS
    assert "WHO A RULE APPLIES TO" in text and "including the opening one" in text
    assert "If a party (including the Claimant) fails to make the deposits" in text
    assert "only where the rule itself names them" in text


def test_rule_attribution_drops_leave_no_empty_numbered_heading():
    provisions = {"5": "5. Miscellaneous expenses shall be determined by the Coordinator and shall be paid "
                       "equally by the parties.",
                  "6": "6. The Coordinator shall maintain an account."}
    answer = ("### 1. Expenses\n- Miscellaneous expenses shall be paid equally by the parties (Rule 5).\n\n"
              "### 2. Accounts\n- The Centre shall refund the account (Rule 6).")
    result, dropped = answer_guard.validate_rule_attribution(answer, provisions)
    assert dropped == 1
    assert "### 2." not in result and "Accounts" not in result
    assert result == "### 1. Expenses\n- Miscellaneous expenses shall be paid equally by the parties (Rule 5)."
