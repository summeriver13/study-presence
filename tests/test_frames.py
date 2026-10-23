from __future__ import annotations

import base64

import cv2
import numpy as np
import pytest

from app.frames import FrameError, encode_jpeg_base64, fit_box, fit_width, to_rgb

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


@pytest.fixture
def frame() -> np.ndarray:
    return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)


def test_fit_width_downscales_keeping_aspect(frame: np.ndarray) -> None:
    resized = fit_width(frame, 640)
    assert resized.shape[:2] == (360, 640)


def test_fit_width_returns_small_frames_untouched(frame: np.ndarray) -> None:
    assert fit_width(frame, FRAME_WIDTH) is frame


def test_fit_box_respects_height_limit() -> None:
    tall = np.zeros((1000, 500, 3), dtype=np.uint8)
    resized = fit_box(tall, 640, 360)
    assert resized.shape[0] <= 360
    assert resized.shape[1] == 180


def test_fit_box_never_upscales() -> None:
    small = np.zeros((100, 100, 3), dtype=np.uint8)
    assert fit_box(small, 640, 360) is small


def test_to_rgb_swaps_channels() -> None:
    bgr = np.array([[[10, 20, 30]]], dtype=np.uint8)
    assert to_rgb(bgr).tolist() == [[[30, 20, 10]]]


def test_encode_jpeg_base64_roundtrip(frame: np.ndarray) -> None:
    decoded = base64.b64decode(encode_jpeg_base64(frame))
    image = cv2.imdecode(np.frombuffer(decoded, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    assert image.shape == frame.shape


def test_encode_fails_on_empty_frame() -> None:
    with pytest.raises((FrameError, cv2.error)):
        encode_jpeg_base64(np.zeros((0, 0, 3), dtype=np.uint8))
