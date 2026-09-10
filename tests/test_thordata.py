from __future__ import annotations

from types import SimpleNamespace

import pytest

from radar.thordata import (
    CreditsExhausted,
    ThordataError,
    _business_error,
    _extract_task_id,
    raise_for_credits,
)

# Respuesta real observada: HTTP 200 con el error de créditos en el cuerpo.
REAL_CREDITS_BODY = {
    "code": 402,
    "data": "Insufficient permissions result in failure to crawl normally. "
    "Please confirm the balance",
}


def test_credits_error_detected_with_http_200() -> None:
    resp = SimpleNamespace(status_code=200, text=str(REAL_CREDITS_BODY))
    with pytest.raises(CreditsExhausted):
        raise_for_credits(resp, REAL_CREDITS_BODY)


def test_business_error_for_non_200_code() -> None:
    with pytest.raises(ThordataError, match="código 500"):
        _business_error({"code": 500, "data": "boom"}, "")


def test_extract_task_id_from_common_shapes() -> None:
    assert _extract_task_id({"data": {"tasks_id": "abc"}}, "") == "abc"
    assert _extract_task_id({"tasks_id": "xyz"}, "") == "xyz"
    with pytest.raises(ThordataError):
        _extract_task_id({"code": 200, "data": "sin id"}, "")
