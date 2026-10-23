"""采集 + 检测 worker：唯一接触相机、检测器、存储的线程，UI 只消费队列。"""

from __future__ import annotations

import contextlib
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.camera import CameraError, CameraSource
from app.detectors.base import Detector, DetectorError
from app.frames import Frame, fit_box, to_rgb
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceEvent, PresenceState, PresenceTracker

READ_RETRY_S: Final[float] = 0.5
MAX_READ_FAILURES: Final[int] = 3
LOOP_IDLE_S: Final[float] = 0.005
JOIN_TIMEOUT_S: Final[float] = 2.0
DEFAULT_DISPLAY_WIDTH: Final[int] = 640
DEFAULT_DISPLAY_HEIGHT: Final[int] = 360


@dataclass(frozen=True, slots=True)
class FrameUpdate:
    rgb: Frame
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    state: PresenceState
    face_count: int | None
    backend: str
    present_seconds_today: float
    error: str | None


class PresenceMonitor:
    """后台线程跑「取帧 → 定期检测 → 状态机 → 入库」，主线程只渲染。"""

    def __init__(
        self,
        *,
        camera: CameraSource,
        detector: Detector,
        tracker: PresenceTracker,
        store: PresenceStore,
        detect_interval_s: float,
        display_width: int = DEFAULT_DISPLAY_WIDTH,
        display_height: int = DEFAULT_DISPLAY_HEIGHT,
    ) -> None:
        self.frames: queue.Queue[FrameUpdate] = queue.Queue(maxsize=1)
        self.statuses: queue.Queue[StatusUpdate] = queue.Queue()
        self._camera = camera
        self._detector = detector
        self._tracker = tracker
        self._store = store
        self._detect_interval_s = detect_interval_s
        self._display_size = (display_width, display_height)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="presence-worker", daemon=True)
        self._session_id: int | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=JOIN_TIMEOUT_S)
        self._close_session(datetime.now())

    def observe(self, frame: Frame, now: datetime) -> StatusUpdate:
        """单次检测 + 状态推进；拆出来便于脱离线程与相机做测试。"""
        face_count, error = self._detect(frame)
        if face_count is None:
            return self._status(None, error=error, now=now)
        event = self._tracker.update(face_count, now)
        if event is not None:
            self._apply_event(event)
        return self._status(face_count, error=None, now=now)

    def _run(self) -> None:
        last_detect_at = 0.0
        read_failures = 0
        while not self._stop.is_set():
            frame = self._read()
            if frame is None:
                read_failures += 1
                if read_failures >= MAX_READ_FAILURES:
                    self._publish(
                        self._status(None, error="相机连续读取失败，采集已停止", now=datetime.now())
                    )
                    return
                self._stop.wait(READ_RETRY_S)
                continue
            read_failures = 0
            self._publish_frame(frame)
            now = time.monotonic()
            if now - last_detect_at < self._detect_interval_s:
                self._stop.wait(LOOP_IDLE_S)
                continue
            last_detect_at = now
            self._publish(self.observe(frame, datetime.now()))

    def _read(self) -> Frame | None:
        try:
            return self._camera.read()
        except CameraError:
            return None

    def _detect(self, frame: Frame) -> tuple[int | None, str | None]:
        try:
            return self._detector.detect(frame), None
        except DetectorError as exc:
            return None, str(exc)

    def _apply_event(self, event: PresenceEvent) -> None:
        if event.state is PresenceState.PRESENT:
            self._session_id = self._store.start_session(self._detector.name, event.changed_at)
            return
        self._close_session(event.changed_at)

    def _close_session(self, ended_at: datetime) -> None:
        session_id, self._session_id = self._session_id, None
        if session_id is not None:
            self._store.end_session(session_id, ended_at)

    def _status(self, face_count: int | None, *, error: str | None, now: datetime) -> StatusUpdate:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return StatusUpdate(
            state=self._tracker.state,
            face_count=face_count,
            backend=self._detector.name,
            present_seconds_today=self._store.seconds_between(day_start, now),
            error=error,
        )

    def _publish_frame(self, frame: Frame) -> None:
        width, height = self._display_size
        rgb = to_rgb(fit_box(frame, width, height))
        _replace_latest(self.frames, FrameUpdate(rgb=rgb.copy(), observed_at=datetime.now()))

    def _publish(self, status: StatusUpdate) -> None:
        self.statuses.put(status)


def _replace_latest(target: queue.Queue[FrameUpdate], item: FrameUpdate) -> None:
    """只保留最新一帧：UI 落后时丢掉旧帧，不排队积压。"""
    try:
        target.put_nowait(item)
    except queue.Full:
        with contextlib.suppress(queue.Empty):
            target.get_nowait()
        target.put_nowait(item)
