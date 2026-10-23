"""判定质量评估：把标注好的视频回放进判定链，算「在座」判定的 precision / recall / F1。

只评估视觉可复现的部分（在座 / 离座）：交互状态来自真实键鼠，不能随视频回放，
所以标注里的 idle 与 active 都按「在座」处理。阈值该取多少应由 --sweep 的曲线决定，
而不是拍脑袋。

标注 CSV 格式：start_s,end_s,label（label 取 absent / idle / active）。
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

import cv2

from app.detectors.base import Detector, DetectorError
from app.frames import Frame
from app.presence.criteria import PresenceCriteria
from app.presence.tracker import PresenceState, PresenceTracker

DEFAULT_STRIDE_S: Final[float] = 1.0
DEFAULT_SAMPLE_S: Final[float] = 0.5
MILLISECONDS_PER_SECOND: Final[float] = 1000.0
ABSENT_LABEL: Final[str] = "absent"
PRESENT_LABELS: Final[frozenset[str]] = frozenset({"present", "idle", "active"})
EPOCH: Final[datetime] = datetime(2026, 1, 1)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Span:
    start_s: float
    end_s: float
    present: bool


@dataclass(frozen=True, slots=True)
class Metrics:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    @property
    def precision(self) -> float:
        return _ratio(self.true_positive, self.true_positive + self.false_positive)

    @property
    def recall(self) -> float:
        return _ratio(self.true_positive, self.true_positive + self.false_negative)

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return _ratio(2 * precision * recall, precision + recall)

    @property
    def accuracy(self) -> float:
        correct = self.true_positive + self.true_negative
        return _ratio(correct, correct + self.false_positive + self.false_negative)


@dataclass(frozen=True, slots=True)
class EvaluationSetup:
    detector: Detector
    criteria: PresenceCriteria
    tracker_factory: Callable[[], PresenceTracker]
    stride_s: float = DEFAULT_STRIDE_S
    sample_s: float = DEFAULT_SAMPLE_S


def load_labels(path: Path) -> list[Span]:
    spans: list[Span] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            label = row["label"].strip().lower()
            if label != ABSENT_LABEL and label not in PRESENT_LABELS:
                raise ValueError(f"未知标注 {label!r}，可选：absent / idle / active")
            spans.append(
                Span(
                    start_s=float(row["start_s"]),
                    end_s=float(row["end_s"]),
                    present=label != ABSENT_LABEL,
                )
            )
    if not spans:
        raise ValueError(f"标注文件为空：{path}")
    return spans


def evaluate_video(video: Path, labels: Sequence[Span], setup: EvaluationSetup) -> Metrics:
    predicted = _predict(video, setup)
    return compare(predicted, labels, sample_s=setup.sample_s)


def sweep_area_ratio(
    video: Path, labels: Sequence[Span], setup: EvaluationSetup, ratios: Sequence[float]
) -> list[tuple[float, Metrics]]:
    """扫描最小人脸面积占比，给出阈值与指标的关系曲线。"""
    rows: list[tuple[float, Metrics]] = []
    for ratio in ratios:
        criteria = PresenceCriteria(roi=setup.criteria.roi, min_face_area_ratio=ratio)
        variant = EvaluationSetup(
            detector=setup.detector,
            criteria=criteria,
            tracker_factory=setup.tracker_factory,
            stride_s=setup.stride_s,
            sample_s=setup.sample_s,
        )
        rows.append((ratio, evaluate_video(video, labels, variant)))
    return rows


def compare(
    predicted: Sequence[Span], truth: Sequence[Span], *, sample_s: float = DEFAULT_SAMPLE_S
) -> Metrics:
    """按固定步长采样两条时间线，累计混淆矩阵。"""
    end_s = max((span.end_s for span in truth), default=0.0)
    true_positive = false_positive = true_negative = false_negative = 0
    for moment in _sample_times(end_s, sample_s):
        expected = _present_at(truth, moment)
        actual = _present_at(predicted, moment)
        if expected and actual:
            true_positive += 1
        elif actual:
            false_positive += 1
        elif expected:
            false_negative += 1
        else:
            true_negative += 1
    return Metrics(true_positive, false_positive, true_negative, false_negative)


def format_metrics(metrics: Metrics) -> str:
    return "\n".join(
        [
            f"在座判定：precision {metrics.precision:.3f}  recall {metrics.recall:.3f}"
            f"  F1 {metrics.f1:.3f}  准确率 {metrics.accuracy:.3f}",
            f"混淆矩阵：TP {metrics.true_positive}  FP {metrics.false_positive}"
            f"  FN {metrics.false_negative}  TN {metrics.true_negative}",
        ]
    )


def format_sweep(rows: Sequence[tuple[float, Metrics]]) -> str:
    lines = ["最小人脸面积占比    precision  recall  F1"]
    lines.extend(
        f"{ratio:<18.3f}  {metrics.precision:>8.3f}  {metrics.recall:>6.3f}  {metrics.f1:.3f}"
        for ratio, metrics in rows
    )
    return "\n".join(lines)


def _predict(video: Path, setup: EvaluationSetup) -> list[Span]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"无法打开视频：{video}")
    tracker = setup.tracker_factory()
    spans: list[Span] = []
    current_start: float | None = None
    next_due = 0.0
    now_s = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            now_s = capture.get(cv2.CAP_PROP_POS_MSEC) / MILLISECONDS_PER_SECOND
            if now_s < next_due:
                continue
            next_due = now_s + setup.stride_s
            occupied = _occupied(frame, setup)
            tracker.update(occupied=occupied, active=True, now=EPOCH + timedelta(seconds=now_s))
            if tracker.state is PresenceState.ABSENT:
                if current_start is not None:
                    spans.append(Span(current_start, now_s, present=True))
                    current_start = None
            elif current_start is None:
                current_start = now_s
    finally:
        capture.release()
    if current_start is not None:
        spans.append(Span(current_start, now_s, present=True))
    return spans


def _occupied(frame: Frame, setup: EvaluationSetup) -> bool:
    try:
        return setup.criteria.occupied(setup.detector.detect(frame))
    except DetectorError:
        logger.warning("单帧检测失败，按离座处理", exc_info=True)
        return False


def _sample_times(end_s: float, sample_s: float) -> list[float]:
    if sample_s <= 0:
        raise ValueError("sample_s 必须为正数")
    count = int(end_s / sample_s) + 1
    return [index * sample_s for index in range(count)]


def _present_at(spans: Sequence[Span], moment: float) -> bool:
    return any(span.present and span.start_s <= moment < span.end_s for span in spans)


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
