"""Backend fee validation for HearingRequestCreate (server.py).

Pure pydantic model test — no DB/HTTP needed, since the validation lives on
the request model itself and must reject fee <= 0 regardless of transport.
"""
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import HearingRequestCreate  # noqa: E402


def _payload(fee):
    return dict(court_id="court_tishazari", hearing_date="2026-08-01", case_details="Test case", fee=fee)


def test_fee_none_is_still_allowed():
    req = HearingRequestCreate(**_payload(None))
    assert req.fee is None


def test_fee_positive_is_accepted():
    req = HearingRequestCreate(**_payload(1500.0))
    assert req.fee == 1500.0


def test_fee_zero_is_rejected():
    with pytest.raises(ValidationError):
        HearingRequestCreate(**_payload(0))


def test_fee_negative_is_rejected():
    with pytest.raises(ValidationError):
        HearingRequestCreate(**_payload(-100))
