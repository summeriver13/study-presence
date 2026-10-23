"""摄像头封装：cv2.VideoCapture 的唯一生命周期入口。"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Final, Self

import cv2

from app.frames import Frame
from app.sources import SourceError

logger = logging.getLogger(__name__)

DEFAULT_CAMERA_INDEX: Final[int] = 0
CAPTURE_WIDTH: Final[int] = 1280
CAPTURE_HEIGHT: Final[int] = 720
WARMUP_READS: Final[int] = 3


class CameraError(SourceError):
    """相机不可用或读取失败。"""


class CameraSource:
    def __init__(self, index: int = DEFAULT_CAMERA_INDEX) -> None:
        self._index = index
        self._capture: cv2.VideoCapture | None = None

    @property
    def index(self) -> int:
        return self._index

    def open(self) -> None:
        if self._capture is not None:
            return
        capture = cv2.VideoCapture(self._index)
        if not capture.isOpened():
            capture.release()
            raise CameraError(f"无法打开摄像头 {self._index}：检查占用情况，或用 --camera 换编号")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
        self._capture = capture
        logger.info(
            "摄像头 %d 就绪：%dx%d",
            self._index,
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        self._warmup()

    def read(self) -> Frame | None:
        capture = self._capture
        if capture is None:
            raise CameraError("相机未打开")
        ok, frame = capture.read()
        if not ok or frame is None:
            return None
        return frame

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()
            logger.info("摄像头 %d 已释放", self._index)

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

    def _warmup(self) -> None:
        """前几帧常为曝光未稳定的黑帧，丢掉。"""
        capture = self._capture
        assert capture is not None
        for _ in range(WARMUP_READS):
            capture.read()
