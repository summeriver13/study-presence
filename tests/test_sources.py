from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.sources import SourceError, VideoFileSource

FRAME_WIDTH = 64
FRAME_HEIGHT = 48
FRAME_COUNT = 5
VIDEO_FPS = 25.0


def write_video(path: Path, frames: int = FRAME_COUNT) -> Path:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter.fourcc(*"MJPG"), VIDEO_FPS, (FRAME_WIDTH, FRAME_HEIGHT)
    )
    try:
        for index in range(frames):
            writer.write(np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), index * 10, dtype=np.uint8))
    finally:
        writer.release()
    return path


def write_image(path: Path) -> Path:
    cv2.imwrite(str(path), np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), 120, dtype=np.uint8))
    return path


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="找不到输入文件"):
        VideoFileSource(tmp_path / "missing.mp4").open()


def test_undecodable_image_is_reported(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    with pytest.raises(SourceError, match="无法解码图片"):
        VideoFileSource(broken).open()


def test_video_loops_after_last_frame(tmp_path: Path) -> None:
    source = VideoFileSource(write_video(tmp_path / "demo.avi"))
    source.open()
    try:
        for _ in range(FRAME_COUNT):
            assert source.read() is not None
        assert source.read() is not None
    finally:
        source.close()


def test_image_source_repeats_the_same_frame(tmp_path: Path) -> None:
    source = VideoFileSource(write_image(tmp_path / "face.jpg"))
    source.open()
    try:
        first = source.read()
        second = source.read()
        assert first is not None
        assert second is not None
        assert first.shape == second.shape
    finally:
        source.close()


def test_read_after_close_is_reported(tmp_path: Path) -> None:
    source = VideoFileSource(write_video(tmp_path / "demo.avi"))
    source.open()
    source.close()
    with pytest.raises(SourceError, match="未打开"):
        source.read()
