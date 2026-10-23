"""在座判据：把检测框筛成「位于画面中央且足够大」的合格人脸。

没有这一步，画面里任意一张脸（海报、屏幕、路过的人、远处的室友）都会被算作在座，
这正是旧实现的最大漏洞。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.detectors.base import DetectionResult, FaceBox

ROI_LEFT: Final[float] = 0.2
ROI_TOP: Final[float] = 0.05
ROI_WIDTH: Final[float] = 0.6
ROI_HEIGHT: Final[float] = 0.9
DEFAULT_ROI: Final[tuple[float, float, float, float]] = (ROI_LEFT, ROI_TOP, ROI_WIDTH, ROI_HEIGHT)
DEFAULT_MIN_FACE_AREA_RATIO: Final[float] = 0.02


@dataclass(frozen=True, slots=True)
class PresenceCriteria:
    roi: tuple[float, float, float, float] = DEFAULT_ROI
    min_face_area_ratio: float = DEFAULT_MIN_FACE_AREA_RATIO

    def qualified_faces(self, result: DetectionResult) -> tuple[FaceBox, ...]:
        return tuple(face for face in result.faces if self._accepts(face))

    def occupied(self, result: DetectionResult) -> bool:
        return bool(self.qualified_faces(result))

    def _accepts(self, face: FaceBox) -> bool:
        if face.area_ratio < self.min_face_area_ratio:
            return False
        center_x, center_y = face.center
        left, top, width, height = self.roi
        return left <= center_x <= left + width and top <= center_y <= top + height
