"""把逐帧的人脸计数去抖成稳定的在座/离座状态。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

DEFAULT_PRESENT_AFTER: Final[int] = 2
DEFAULT_ABSENT_AFTER: Final[int] = 3
_MISSING_FACE_COUNT: Final[int] = 0


class PresenceState(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class PresenceEvent:
    state: PresenceState
    changed_at: datetime


class PresenceTracker:
    """连续 N 次观测才切换状态，抑制检测抖动与短暂离开。"""

    def __init__(
        self,
        *,
        present_after: int = DEFAULT_PRESENT_AFTER,
        absent_after: int = DEFAULT_ABSENT_AFTER,
        initial: PresenceState = PresenceState.ABSENT,
    ) -> None:
        if present_after < 1 or absent_after < 1:
            raise ValueError("present_after 与 absent_after 必须 >= 1")
        self._present_after = present_after
        self._absent_after = absent_after
        self._state = initial
        self._streak = 0

    @property
    def state(self) -> PresenceState:
        return self._state

    def update(self, face_count: int, now: datetime) -> PresenceEvent | None:
        """喂入一次观测，状态真正翻转时返回事件。"""
        observed_present = face_count > _MISSING_FACE_COUNT
        if observed_present == (self._state is PresenceState.PRESENT):
            self._streak = 0
            return None

        self._streak += 1
        threshold = self._absent_after if self._state is PresenceState.PRESENT else self._present_after
        if self._streak < threshold:
            return None

        self._state = PresenceState.ABSENT if self._state is PresenceState.PRESENT else PresenceState.PRESENT
        self._streak = 0
        return PresenceEvent(state=self._state, changed_at=now)
