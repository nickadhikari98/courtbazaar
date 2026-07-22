"""Candidate Scoring Engine (roadmap M6).

Unlike every other test file in this Counsel Matching Agent series,
score_candidates does no I/O at all — no Mongo, no asyncio needed. These are
plain synchronous unit tests over in-memory dicts.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402


HEARING = {"hearing_id": "test_hearing_1", "court_id": "court_tishazari"}


def _counsel(user_id="c1", rating=0, cases_completed=0, experience_years=0,
             instant_booking=False, courts=None):
    return {
        "user_id": user_id,
        "rating": rating,
        "cases_completed": cases_completed,
        "experience_years": experience_years,
        "instant_booking": instant_booking,
        "courts": courts or [],
    }


def test_score_candidates_empty_list_returns_empty():
    assert counsel_matching.score_candidates(HEARING, []) == []


def test_score_candidates_attaches_confidence_score_in_range():
    candidates = [_counsel(rating=4, cases_completed=10, experience_years=5, instant_booking=True,
                            courts=["court_tishazari"])]
    result = counsel_matching.score_candidates(HEARING, candidates)
    assert len(result) == 1
    assert "confidence_score" in result[0]
    assert 0.0 <= result[0]["confidence_score"] <= 1.0


def test_score_candidates_sorts_highest_first():
    weak = _counsel(user_id="weak", rating=1, cases_completed=0, experience_years=0)
    strong = _counsel(user_id="strong", rating=5, cases_completed=25, experience_years=15,
                       instant_booking=True, courts=["court_tishazari"])
    result = counsel_matching.score_candidates(HEARING, [weak, strong])
    assert [c["user_id"] for c in result] == ["strong", "weak"]
    assert result[0]["confidence_score"] > result[1]["confidence_score"]


def test_court_match_increases_score_all_else_equal():
    base = dict(rating=3, cases_completed=5, experience_years=3, instant_booking=False)
    matched = _counsel(user_id="matched", courts=["court_tishazari"], **base)
    unmatched = _counsel(user_id="unmatched", courts=["court_saket"], **base)
    result = counsel_matching.score_candidates(HEARING, [unmatched, matched])
    scores = {c["user_id"]: c["confidence_score"] for c in result}
    assert scores["matched"] > scores["unmatched"]
    # Difference should be exactly the court_match weight (0.25) since
    # everything else is identical between the two candidates.
    assert round(scores["matched"] - scores["unmatched"], 4) == 0.25


def test_score_candidates_handles_missing_optional_fields():
    bare = {"user_id": "bare_profile"}  # no rating/cases_completed/experience_years/instant_booking/courts at all
    result = counsel_matching.score_candidates(HEARING, [bare])
    assert result[0]["confidence_score"] == 0.0  # every factor defaults to its floor


def test_score_candidates_does_not_mutate_input():
    original = _counsel(user_id="c1", rating=3)
    original_copy = dict(original)
    counsel_matching.score_candidates(HEARING, [original])
    assert original == original_copy
    assert "confidence_score" not in original


def test_saturating_factors_cap_at_one():
    maxed_out = _counsel(cases_completed=1000, experience_years=100, rating=100)
    result = counsel_matching.score_candidates(HEARING, [maxed_out])
    # rating/cases_completed/experience_years factors should each cap at 1.0,
    # so with instant_booking off and no court match the total is exactly
    # the sum of the other three weights (0.35 + 0.20 + 0.10).
    assert result[0]["confidence_score"] == 0.65


def test_scoring_weights_sum_to_one():
    total = sum(weight for _, weight, _ in counsel_matching.SCORING_FACTORS)
    assert round(total, 6) == 1.0
