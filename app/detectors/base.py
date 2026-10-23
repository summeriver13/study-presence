"""检测后端的契约：输入一帧 BGR 图，返回人脸数量。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.frames import Frame


class DetectorError(RuntimeError):
    """后端不可用、鉴权失败或返回错误。"""


@runtime_checkable
class Detector(Protocol):
    name: str

    def detect(self, frame: Frame) -> int:
        """返回画面中的人脸数；失败时抛 DetectorError，不吞异常。"""
        ...
