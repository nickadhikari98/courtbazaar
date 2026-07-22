"""Notification Batch Preparation (roadmap M8).

Like the M6/M7 test files, prepare_notification_batch does no I/O at all —
plain synchronous unit tests over in-memory dicts.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import counsel_matching  # noqa: E402


HEARING = {
    "hearing_id": "test_hearing_1",
    "court_id": "court_tishazari",
    "hearing_date": "2026-08-01",
    "fee": 1500.0,
}


def _selected(user_id, confidence_score):
    return {"user_id": user_id, "confidence_score": confidence_score}


def test_basic_shape_and_values():
    result = counsel_matching.prepare_notification_batch(HEARING, [_selected("c1", 0.8)])
    assert len(result) == 1
    entry = result[0]
    assert entry["counsel_user_id"] == "c1"
    assert entry["hearing_id"] == "test_hearing_1"
    assert entry["court_id"] == "court_tishazari"
    assert entry["hearing_date"] == "2026-08-01"
    assert entry["fee"] == 1500.0
    assert entry["confidence_score"] == 0.8
    assert entry["event_type"] == "hearing_offer"


def test_preserves_order():
    candidates = [_selected("c1", 0.9), _selected("c2", 0.7), _selected("c3", 0.5)]
    result = counsel_matching.prepare_notification_batch(HEARING, candidates)
    assert [e["counsel_user_id"] for e in result] == ["c1", "c2", "c3"]


def test_empty_list_returns_empty():
    assert counsel_matching.prepare_notification_batch(HEARING, []) == []


def test_does_not_mutate_candidates_or_hearing():
    candidates = [_selected("c1", 0.8)]
    original_candidates = [dict(c) for c in candidates]
    original_hearing = dict(HEARING)
    counsel_matching.prepare_notification_batch(HEARING, candidates)
    assert candidates == original_candidates
    assert HEARING == original_hearing


def test_default_event_type_is_hearing_offer():
    result = counsel_matching.prepare_notification_batch(HEARING, [_selected("c1", 0.8)])
    assert result[0]["event_type"] == counsel_matching.NOTIFICATION_EVENT_TYPE == "hearing_offer"


def test_custom_event_type_override():
    result = counsel_matching.prepare_notification_batch(
        HEARING, [_selected("c1", 0.8)], event_type="hearing_rebroadcast",
    )
    assert result[0]["event_type"] == "hearing_rebroadcast"


def test_handles_missing_optional_hearing_fields():
    bare_hearing = {"hearing_id": "test_hearing_2"}  # no court_id/hearing_date/fee at all
    result = counsel_matching.prepare_notification_batch(bare_hearing, [_selected("c1", 0.8)])
    entry = result[0]
    assert entry["hearing_id"] == "test_hearing_2"
    assert entry["court_id"] is None
    assert entry["hearing_date"] is None
    assert entry["fee"] is None


def test_no_urgent_or_case_details_leaked_into_payload():
    hearing_with_extra_fields = {**HEARING, "urgent": True, "case_details": "sensitive free text"}
    result = counsel_matching.prepare_notification_batch(hearing_with_extra_fields, [_selected("c1", 0.8)])
    assert "urgent" not in result[0]
    assert "case_details" not in result[0]


def test_composes_with_full_pipeline_end_to_end():
    raw = [
        {"user_id": "weak", "rating": 1, "cases_completed": 0, "experience_years": 0,
         "instant_booking": False, "courts": []},
        {"user_id": "strong", "rating": 5, "cases_completed": 25, "experience_years": 15,
         "instant_booking": True, "courts": ["court_tishazari"]},
    ]
    scored = counsel_matching.score_candidates(HEARING, raw)
    top = counsel_matching.select_top_candidates(HEARING, scored, batch_size=1)
    batch = counsel_matching.prepare_notification_batch(HEARING, top)
    assert len(batch) == 1
    assert batch[0]["counsel_user_id"] == "strong"
    assert batch[0]["hearing_id"] == "test_hearing_1"
