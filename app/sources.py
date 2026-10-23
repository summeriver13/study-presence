"""帧来源：摄像头与视频/图片文件共用 open/read/close 接口。"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol, Self, runtime_checkable

import cv2

from app.frames import Frame

IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
FALLBACK_FPS: Final[float] = 15.0
MAX_PACE_SLEEP_S: Final[float] = 0.2


class SourceError(RuntimeError):
    """帧来源不可用。"""


@runtime_checkable
class FrameSource(Protocol):
    def open(self) -> None: ...

    def read(self) -> Frame | None: ...

    def close(self) -> None: ...


class VideoFileSource:
    """无摄像头时的演示输入：视频循环播放，图片持续复用同一帧。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._capture: cv2.VideoCapture | None = None
        self._image: Frame | None = None
        self._frame_interval_s = 0.0
        self._next_frame_at = 0.0

    @property
    def path(self) -> Path:
        return self._path

    def open(self) -> None:
        if not self._path.is_file():
            raise SourceError(f"找不到输入文件：{self._path}")
        if self._path.suffix.lower() in IMAGE_SUFFIXES:
            self._open_image()
            return
        self._open_video()

    def read(self) -> Frame | None:
        self._pace()
        if self._image is not None:
            return self._image
        return self._read_video_frame()

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()
        self._image = None

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _open_image(self) -> None:
        image = cv2.imread(str(self._path))
        if image is None:
            raise SourceError(f"无法解码图片：{self._path}")
        self._image = image
        self._frame_interval_s = 1.0 / FALLBACK_FPS

    def _open_video(self) -> None:
        capture = cv2.VideoCapture(str(self._path))
        if not capture.isOpened():
            capture.release()
            raise SourceError(f"无法打开视频：{self._path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        self._capture = capture
        self._frame_interval_s = 1.0 / fps if fps and fps > 0 else 1.0 / FALLBACK_FPS

    def _read_video_frame(self) -> Frame | None:
        capture = self._capture
        if capture is None:
            raise SourceError("输入源未打开")
        ok, frame = capture.read()
        if ok and frame is not None:
            return frame
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = capture.read()
        return frame if ok and frame is not None else None

    def _pace(self) -> None:
        """按文件帧率出帧，避免演示时把 CPU 空转在解码上。"""
        if self._frame_interval_s <= 0:
            return
        delay = self._next_frame_at - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, MAX_PACE_SLEEP_S))
        self._next_frame_at = time.monotonic() + self._frame_interval_s
