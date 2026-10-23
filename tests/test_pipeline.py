from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from app.activity import NullActivitySource
from app.detectors.base import DetectionResult, DetectorError, FaceBox
from app.frames import Frame
from app.pipeline import PresenceMonitor
from app.presence.criteria import PresenceCriteria
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceState, PresenceTracker
from app.sources import FrameSource

FRAME = np.zeros((240, 320, 3), dtype=np.uint8)
NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
CENTER_FACE = FaceBox(x=0.4, y=0.2, width=0.2, height=0.3)
PRESENT_AFTER_S = 1.0
ACTIVITY_IDLE_S = 60.0


class FakeDetector:
    name = "fake:detector"

    def __init__(self, occupied: list[bool] | None = None, error: str | None = None) -> None:
        self._occupied = occupied or []
        self._error = error

    def detect(self, frame: Frame) -> DetectionResult:
        if self._error is not None:
            raise DetectorError(self._error)
        return DetectionResult((CENTER_FACE,)) if self._occupied.pop(0) else DetectionResult()


class FakeActivity:
    available = True

    def __init__(self, idle_values: list[float | None] | None = None) -> None:
        self._values = idle_values or []
        self._last: float | None = 1.0

    def idle_seconds(self) -> float | None:
        if self._values:
            self._last = self._values.pop(0)
        return self._last


class SilentCamera:
    def read(self) -> Frame | None:
        return None


@pytest.fixture
def store(tmp_path: Path) -> Iterator[PresenceStore]:
    store = PresenceStore(tmp_path / "presence.db")
    yield store
    store.close()


def build_monitor(
    store: PresenceStore, detector: FakeDetector, activity: FakeActivity | NullActivitySource | None = None
) -> PresenceMonitor:
    return PresenceMonitor(
        source=cast(FrameSource, SilentCamera()),
        detector=detector,
        tracker=PresenceTracker(present_after_s=PRESENT_AFTER_S, absent_after_s=PRESENT_AFTER_S),
        store=store,
        criteria=PresenceCriteria(),
        activity=activity or FakeActivity(),
        detect_interval_s=1.0,
        activity_idle_s=ACTIVITY_IDLE_S,
    )


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def test_present_with_input_becomes_active(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([True, True, True]))
    monitor.observe(FRAME, at(0))
    status = monitor.observe(FRAME, at(1))
    assert status.state is PresenceState.ACTIVE
    assert status.activity_available
    assert status.present_seconds_today == pytest.approx(0.0)
    assert monitor.observe(FRAME, at(2)).active_seconds_today == pytest.approx(1.0)


def test_present_without_input_is_idle_not_active(store: PresenceStore) -> None:
    activity = FakeActivity([ACTIVITY_IDLE_S + 5, ACTIVITY_IDLE_S + 9])
    monitor = build_monitor(store, FakeDetector([True, True, True]), activity)
    monitor.observe(FRAME, at(0))
    status = monitor.observe(FRAME, at(1))
    assert status.state is PresenceState.IDLE
    status = monitor.observe(FRAME, at(2))
    assert status.present_seconds_today == pytest.approx(1.0)
    assert status.active_seconds_today == pytest.approx(0.0)


def test_missing_activity_source_does_not_penalise(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([True, True]), NullActivitySource())
    monitor.observe(FRAME, at(0))
    status = monitor.observe(FRAME, at(1))
    assert status.state is PresenceState.ACTIVE
    assert not status.activity_available


def test_state_change_splits_sessions(store: PresenceStore) -> None:
    activity = FakeActivity([1.0, 1.0, ACTIVITY_IDLE_S + 5])
    monitor = build_monitor(store, FakeDetector([True, True, True]), activity)
    monitor.observe(FRAME, at(0))
    monitor.observe(FRAME, at(1))
    monitor.observe(FRAME, at(2))
    records = store.sessions_between(at(-1), at(10))
    assert [record.state for record in records] == ["active", "idle"]


def test_leaving_closes_session(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([True, True, False, False]))
    monitor.observe(FRAME, at(0))
    monitor.observe(FRAME, at(1))
    monitor.observe(FRAME, at(2))
    status = monitor.observe(FRAME, at(3))
    assert status.state is PresenceState.ABSENT
    assert status.present_seconds_today == pytest.approx(2.0)


def test_detector_error_is_surfaced(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector(error="quota exceeded"))
    status = monitor.observe(FRAME, NOW)
    assert status.error == "quota exceeded"
    assert status.face_count is None
    assert status.state is PresenceState.ABSENT
    assert status.detect_ms is not None


def test_repeated_read_failures_stop_collection(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([True]))
    monitor._run()
    statuses = []
    while not monitor.statuses.empty():
        statuses.append(monitor.statuses.get_nowait())
    assert statuses
    assert "读取失败" in (statuses[-1].error or "")
