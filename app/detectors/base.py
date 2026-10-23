"""检测后端的公共契约：一次检测返回归一化的人脸框。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.frames import Frame


class DetectorError(RuntimeError):
    """检测后端不可用或返回错误。"""


@dataclass(frozen=True, slots=True)
class FaceBox:
    """归一化人脸框：x/y 为左上角，宽高与坐标都相对检测帧的边长。"""

    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    @property
    def area_ratio(self) -> float:
        """人脸框占整帧面积的比例，用于过滤远处的脸。"""
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class DetectionResult:
    faces: tuple[FaceBox, ...] = ()

    @property
    def face_count(self) -> int:
        return len(self.faces)


@runtime_checkable
class Detector(Protocol):
    name: str

    def detect(self, frame: Frame) -> DetectionResult: ...
