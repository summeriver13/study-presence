"""把逐帧观测去抖成「离座 / 在座无交互 / 在座有交互」三态。

占据判定用时间窗去抖（与检测间隔解耦），交互状态即时反映：只要最近一次观测
仍有键鼠活动就算「有交互」，一旦空闲超过阈值就退回「在座无交互」。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

DEFAULT_PRESENT_AFTER_S: Final[float] = 4.0
DEFAULT_ABSENT_AFTER_S: Final[float] = 6.0


class PresenceState(StrEnum):
    ABSENT = "absent"
    IDLE = "idle"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class PresenceEvent:
    state: PresenceState
    changed_at: datetime


class PresenceTracker:
    def __init__(
        self,
        *,
        present_after_s: float = DEFAULT_PRESENT_AFTER_S,
        absent_after_s: float = DEFAULT_ABSENT_AFTER_S,
        initial: PresenceState = PresenceState.ABSENT,
    ) -> None:
        if present_after_s <= 0 or absent_after_s <= 0:
            raise ValueError("去抖阈值必须为正数")
        self._present_after_s = present_after_s
        self._absent_after_s = absent_after_s
        self._occupied = initial is not PresenceState.ABSENT
        self._state = initial
        self._pending: bool | None = None
        self._pending_since: datetime | None = None

    @property
    def state(self) -> PresenceState:
        return self._state

    def update(self, *, occupied: bool, active: bool, now: datetime) -> PresenceEvent | None:
        """喂入一次观测，最终状态真正变化时返回事件。"""
        self._advance_occupancy(occupied, now)
        state = self._state_for(active)
        if state is self._state:
            return None
        self._state = state
        return PresenceEvent(state=state, changed_at=now)

    def _state_for(self, active: bool) -> PresenceState:
        if not self._occupied:
            return PresenceState.ABSENT
        return PresenceState.ACTIVE if active else PresenceState.IDLE

    def _advance_occupancy(self, occupied: bool, now: datetime) -> None:
        if occupied == self._occupied:
            self._pending = None
            self._pending_since = None
            return
        if self._pending is not occupied or self._pending_since is None:
            self._pending = occupied
            self._pending_since = now
            return
        elapsed = (now - self._pending_since).total_seconds()
        threshold = self._present_after_s if occupied else self._absent_after_s
        if elapsed < threshold:
            return
        self._occupied = occupied
        self._pending = None
        self._pending_since = None
