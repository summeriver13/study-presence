"""采集 + 检测 worker：唯一接触相机、检测器、存储的线程，UI 只消费队列。"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.activity import ActivitySource
from app.detectors.base import DetectionResult, Detector, DetectorError
from app.frames import Frame, fit_box, to_rgb
from app.presence.criteria import PresenceCriteria
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceEvent, PresenceState, PresenceTracker
from app.sources import FrameSource, SourceError

READ_RETRY_S: Final[float] = 0.5
MAX_READ_FAILURES: Final[int] = 3
LOOP_IDLE_S: Final[float] = 0.005
JOIN_TIMEOUT_S: Final[float] = 2.0
DEFAULT_DISPLAY_WIDTH: Final[int] = 640
DEFAULT_DISPLAY_HEIGHT: Final[int] = 360
MILLISECONDS_PER_SECOND: Final[float] = 1000.0

logger = logging.getLogger(__name__)


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
    active_seconds_today: float
    error: str | None
    detect_ms: float | None
    activity_available: bool


class PresenceMonitor:
    """后台线程跑「取帧 → 定期检测 → 判据 → 状态机 → 入库」，主线程只渲染。"""

    def __init__(
        self,
        *,
        source: FrameSource,
        detector: Detector,
        tracker: PresenceTracker,
        store: PresenceStore,
        criteria: PresenceCriteria,
        activity: ActivitySource,
        detect_interval_s: float,
        activity_idle_s: float,
        display_width: int = DEFAULT_DISPLAY_WIDTH,
        display_height: int = DEFAULT_DISPLAY_HEIGHT,
    ) -> None:
        self.frames: queue.Queue[FrameUpdate] = queue.Queue(maxsize=1)
        self.statuses: queue.Queue[StatusUpdate] = queue.Queue()
        self._source = source
        self._detector = detector
        self._tracker = tracker
        self._store = store
        self._criteria = criteria
        self._activity = activity
        self._detect_interval_s = detect_interval_s
        self._activity_idle_s = activity_idle_s
        self._display_size = (display_width, display_height)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="presence-worker", daemon=True)
        self._session_id: int | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread.start()
        logger.info("采集线程启动：来源 %s，后端 %s", self._source_name(), self._detector.name)

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=JOIN_TIMEOUT_S)
        self._close_session(datetime.now())
        logger.info("采集线程停止")

    def observe(self, frame: Frame, now: datetime) -> StatusUpdate:
        """单次检测 + 状态推进；拆出来便于脱离线程与相机做测试。"""
        started_at = time.perf_counter()
        result, error = self._detect(frame)
        detect_ms = (time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND
        if result is None:
            return self._status(None, error=error, now=now, detect_ms=detect_ms)
        event = self._tracker.update(occupied=self._criteria.occupied(result), active=self._active(), now=now)
        if event is not None:
            self._apply_event(event)
        return self._status(result.face_count, error=None, now=now, detect_ms=detect_ms)

    def _run(self) -> None:
        last_detect_at = 0.0
        read_failures = 0
        while not self._stop.is_set():
            frame = self._read()
            if frame is None:
                read_failures += 1
                if read_failures >= MAX_READ_FAILURES:
                    logger.error("输入源连续 %d 次读取失败，采集停止", read_failures)
                    self._publish(
                        self._status(
                            None,
                            error="输入源连续读取失败，采集已停止",
                            now=datetime.now(),
                            detect_ms=None,
                        )
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

    def _active(self) -> bool:
        """有交互证据才算 active；平台不支持时不惩罚（在座即视为有交互）。"""
        idle = self._activity.idle_seconds()
        if idle is None:
            return True
        return idle <= self._activity_idle_s

    def _read(self) -> Frame | None:
        try:
            return self._source.read()
        except SourceError:
            return None

    def _detect(self, frame: Frame) -> tuple[DetectionResult | None, str | None]:
        try:
            return self._detector.detect(frame), None
        except DetectorError as exc:
            self._log_detector_error(str(exc))
            return None, str(exc)

    def _log_detector_error(self, message: str) -> None:
        """同一错误只记一次，避免按检测间隔刷屏。"""
        if message != self._last_error:
            logger.warning("检测失败：%s", message)
            self._last_error = message

    def _apply_event(self, event: PresenceEvent) -> None:
        logger.info("状态切换：%s", event.state.value)
        self._close_session(event.changed_at)
        if event.state is PresenceState.ABSENT:
            return
        self._session_id = self._store.start_session(self._detector.name, event.state.value, event.changed_at)

    def _close_session(self, ended_at: datetime) -> None:
        session_id, self._session_id = self._session_id, None
        if session_id is not None:
            self._store.end_session(session_id, ended_at)

    def _source_name(self) -> str:
        return str(getattr(self._source, "path", type(self._source).__name__))

    def _status(
        self, face_count: int | None, *, error: str | None, now: datetime, detect_ms: float | None
    ) -> StatusUpdate:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return StatusUpdate(
            state=self._tracker.state,
            face_count=face_count,
            backend=self._detector.name,
            present_seconds_today=self._store.seconds_between(day_start, now),
            active_seconds_today=self._store.seconds_between(
                day_start, now, state=PresenceState.ACTIVE.value
            ),
            error=error,
            detect_ms=detect_ms,
            activity_available=self._activity.available,
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
