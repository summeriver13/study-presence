from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app.detectors.baidu import BaiduDetector
from app.detectors.base import DetectorError

FRAME = np.zeros((120, 160, 3), dtype=np.uint8)
TOKEN_RESPONSE = {"access_token": "token-1", "expires_in": 2592000}
LOCATION = {"left": 16, "top": 24, "width": 32, "height": 48}


def detect_response(face_count: int) -> dict[str, Any]:
    return {
        "error_code": 0,
        "result": {
            "face_num": face_count,
            "face_list": [{"location": LOCATION} for _ in range(face_count)],
        },
    }


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        return FakeResponse(self._responses.pop(0))


def test_token_is_requested_once_and_reused() -> None:
    session = FakeSession([TOKEN_RESPONSE, detect_response(2), detect_response(1)])
    detector = BaiduDetector("ak", "sk", session=session)  # type: ignore[arg-type]
    assert detector.detect(FRAME).face_count == 2
    assert detector.detect(FRAME).face_count == 1
    assert sum("oauth" in url for url in session.calls) == 1


def test_faces_are_normalized_to_upload_size() -> None:
    session = FakeSession([TOKEN_RESPONSE, detect_response(1)])
    detector = BaiduDetector("ak", "sk", session=session)  # type: ignore[arg-type]
    face = detector.detect(FRAME).faces[0]
    assert face.x == pytest.approx(16 / 160)
    assert face.y == pytest.approx(24 / 120)
    assert face.width == pytest.approx(32 / 160)
    assert face.height == pytest.approx(48 / 120)


def test_invalid_token_triggers_refresh_once() -> None:
    session = FakeSession(
        [
            TOKEN_RESPONSE,
            {"error_code": 110, "error_msg": "token invalid"},
            {"access_token": "token-2", "expires_in": 2592000},
            detect_response(1),
        ]
    )
    detector = BaiduDetector("ak", "sk", session=session)  # type: ignore[arg-type]
    assert detector.detect(FRAME).face_count == 1
    assert sum("oauth" in url for url in session.calls) == 2


def test_missing_location_is_reported() -> None:
    session = FakeSession([TOKEN_RESPONSE, {"error_code": 0, "result": {"face_num": 1, "face_list": []}}])
    detector = BaiduDetector("ak", "sk", session=session)  # type: ignore[arg-type]
    with pytest.raises(DetectorError, match="人脸位置"):
        detector.detect(FRAME)


def test_api_error_is_raised_not_swallowed() -> None:
    session = FakeSession([TOKEN_RESPONSE, {"error_code": 216201, "error_msg": "image format error"}])
    detector = BaiduDetector("ak", "sk", session=session)  # type: ignore[arg-type]
    with pytest.raises(DetectorError, match="216201"):
        detector.detect(FRAME)


def test_missing_token_is_reported() -> None:
    session = FakeSession([{"error": "invalid_client", "error_description": "unknown client id"}])
    detector = BaiduDetector("ak", "sk", session=session)  # type: ignore[arg-type]
    with pytest.raises(DetectorError, match="鉴权失败"):
        detector.detect(FRAME)
