from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from app.camera import CameraSource
from app.detectors.base import DetectorError
from app.frames import Frame
from app.pipeline import PresenceMonitor
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceState, PresenceTracker

FRAME = np.zeros((240, 320, 3), dtype=np.uint8)
NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


class FakeDetector:
    name = "fake:detector"

    def __init__(self, face_counts: list[int] | None = None, error: str | None = None) -> None:
        self._face_counts = face_counts or []
        self._error = error

    def detect(self, frame: Frame) -> int:
        if self._error is not None:
            raise DetectorError(self._error)
        return self._face_counts.pop(0)


class SilentCamera:
    def read(self) -> Frame | None:
        return None


@pytest.fixture
def store(tmp_path: Path) -> Iterator[PresenceStore]:
    store = PresenceStore(tmp_path / "presence.db")
    yield store
    store.close()


def build_monitor(store: PresenceStore, detector: FakeDetector) -> PresenceMonitor:
    return PresenceMonitor(
        camera=cast(CameraSource, SilentCamera()),
        detector=detector,
        tracker=PresenceTracker(present_after=1, absent_after=1),
        store=store,
        detect_interval_s=1.0,
    )


def test_present_detection_opens_session(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([1]))
    status = monitor.observe(FRAME, NOW)
    assert status.state is PresenceState.PRESENT
    assert status.face_count == 1
    assert status.backend == "fake:detector"
    assert store.seconds_between(NOW, NOW) == pytest.approx(0.0)


def test_leaving_closes_session(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([1, 0]))
    monitor.observe(FRAME, NOW)
    status = monitor.observe(FRAME, NOW.replace(minute=1))
    assert status.state is PresenceState.ABSENT
    assert store.seconds_between(NOW, NOW.replace(minute=1)) == pytest.approx(60.0)


def test_stop_closes_open_session(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([1]))
    monitor.observe(FRAME, NOW)
    monitor.stop()
    baseline = store.seconds_between(NOW, datetime.now())
    assert baseline >= 0.0


def test_detector_error_is_surfaced(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector(error="quota exceeded"))
    status = monitor.observe(FRAME, NOW)
    assert status.error == "quota exceeded"
    assert status.face_count is None
    assert status.state is PresenceState.ABSENT


def test_repeated_read_failures_stop_collection(store: PresenceStore) -> None:
    monitor = build_monitor(store, FakeDetector([1]))
    monitor._run()
    statuses = []
    while not monitor.statuses.empty():
        statuses.append(monitor.statuses.get_nowait())
    assert statuses
    assert "读取失败" in (statuses[-1].error or "")
