"""Top Candidate Selection (roadmap M7).

Like test_counsel_matching_scoring.py, select_top_candidates does no I/O at
all — plain synchronous unit tests over in-memory dicts.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402


HEARING = {"hearing_id": "test_hearing_1", "court_id": "court_tishazari"}


def _scored(user_id, score):
    return {"user_id": user_id, "confidence_score": score}


def test_default_batch_size_selects_five():
    candidates = [_scored(f"c{i}", 1.0 - i * 0.1) for i in range(8)]
    result = counsel_matching.select_top_candidates(HEARING, candidates)
    assert len(result) == 5
    assert [c["user_id"] for c in result] == ["c0", "c1", "c2", "c3", "c4"]


def test_fewer_than_batch_size_returns_all():
    candidates = [_scored("c1", 0.9), _scored("c2", 0.5)]
    result = counsel_matching.select_top_candidates(HEARING, candidates)
    assert result == candidates


def test_empty_list_returns_empty():
    assert counsel_matching.select_top_candidates(HEARING, []) == []


def test_custom_batch_size_override():
    candidates = [_scored(f"c{i}", 1.0 - i * 0.1) for i in range(8)]
    result = counsel_matching.select_top_candidates(HEARING, candidates, batch_size=2)
    assert [c["user_id"] for c in result] == ["c0", "c1"]


def test_does_not_resort_trusts_input_order():
    # Deliberately NOT sorted by score — confirms this function trusts
    # whatever order it's given rather than re-deriving one itself.
    candidates = [_scored("low", 0.1), _scored("high", 0.9), _scored("mid", 0.5)]
    result = counsel_matching.select_top_candidates(HEARING, candidates, batch_size=2)
    assert [c["user_id"] for c in result] == ["low", "high"]


def test_does_not_mutate_scores_or_input_list():
    candidates = [_scored("c1", 0.7), _scored("c2", 0.3)]
    original = [dict(c) for c in candidates]
    result = counsel_matching.select_top_candidates(HEARING, candidates, batch_size=1)
    assert candidates == original  # input list/dicts untouched
    assert result[0]["confidence_score"] == 0.7  # score unchanged


def test_batch_size_zero_returns_empty():
    candidates = [_scored("c1", 0.9)]
    assert counsel_matching.select_top_candidates(HEARING, candidates, batch_size=0) == []


def test_negative_batch_size_clamped_to_empty_not_python_slice_semantics():
    candidates = [_scored("c1", 0.9), _scored("c2", 0.5), _scored("c3", 0.1)]
    # Plain candidates[:-1] would return the first two; the clamp must
    # prevent that confusing behavior and return [] instead.
    result = counsel_matching.select_top_candidates(HEARING, candidates, batch_size=-1)
    assert result == []


def test_composes_with_score_candidates_end_to_end():
    raw = [
        {"user_id": "weak", "rating": 1, "cases_completed": 0, "experience_years": 0,
         "instant_booking": False, "courts": []},
        {"user_id": "strong", "rating": 5, "cases_completed": 25, "experience_years": 15,
         "instant_booking": True, "courts": ["court_tishazari"]},
        {"user_id": "mid", "rating": 3, "cases_completed": 5, "experience_years": 3,
         "instant_booking": False, "courts": []},
    ]
    scored = counsel_matching.score_candidates(HEARING, raw)
    top = counsel_matching.select_top_candidates(HEARING, scored, batch_size=2)
    assert [c["user_id"] for c in top] == ["strong", "mid"]
