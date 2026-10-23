"""python -m app / study-presence：解析参数、装配依赖，启动窗口、打印报表或跑评估。"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Final

from app.activity import build_activity_source
from app.camera import CameraSource
from app.config.settings import BACKENDS, ConfigError, Settings
from app.detectors import build_detector
from app.detectors.base import DetectorError
from app.evaluation import (
    DEFAULT_SAMPLE_S,
    DEFAULT_STRIDE_S,
    EvaluationSetup,
    evaluate_video,
    format_metrics,
    format_sweep,
    load_labels,
    sweep_area_ratio,
)
from app.pipeline import DEFAULT_DISPLAY_HEIGHT, DEFAULT_DISPLAY_WIDTH, PresenceMonitor
from app.presence.criteria import PresenceCriteria
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceTracker
from app.report import MIN_DAYS, daily_totals, render_text, report_window, write_csv
from app.sources import FrameSource, SourceError, VideoFileSource
from app.ui.window import StudyPresenceWindow

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
EXIT_OK: Final[int] = 0
EXIT_FAILURE: Final[int] = 1
RATIO_SEPARATOR: Final[str] = ","


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=LOG_FORMAT)
    try:
        settings = _apply_overrides(Settings.from_env(), args)
        if args.evaluate is not None:
            return _run_evaluation(settings, args)
        if args.report is not None:
            return _run_report(settings, days=args.report, csv_path=args.csv)
        return _run_window(settings)
    except (ConfigError, SourceError, DetectorError, ValueError, OSError) as exc:
        logging.error("%s", exc)
        return EXIT_FAILURE


def _run_window(settings: Settings) -> int:
    detector = build_detector(settings)
    source = _build_source(settings)
    store = PresenceStore(settings.db_path)
    try:
        source.open()
        monitor = PresenceMonitor(
            source=source,
            detector=detector,
            tracker=_build_tracker(settings),
            store=store,
            criteria=_build_criteria(settings),
            activity=build_activity_source(settings.track_input),
            detect_interval_s=settings.detect_interval_s,
            activity_idle_s=settings.activity_idle_s,
            display_width=DEFAULT_DISPLAY_WIDTH,
            display_height=DEFAULT_DISPLAY_HEIGHT,
        )
        StudyPresenceWindow(
            monitor, display_width=DEFAULT_DISPLAY_WIDTH, display_height=DEFAULT_DISPLAY_HEIGHT
        ).run()
    finally:
        source.close()
        store.close()
    return EXIT_OK


def _run_report(settings: Settings, *, days: int, csv_path: Path | None) -> int:
    store = PresenceStore(settings.db_path)
    try:
        window_start, window_end = report_window(days, datetime.now())
        sessions = store.sessions_between(window_start, window_end)
        totals = daily_totals(sessions, window_start, window_end)
    finally:
        store.close()
    print(render_text(totals))
    if csv_path is not None:
        write_csv(totals, csv_path)
    return EXIT_OK


def _run_evaluation(settings: Settings, args: argparse.Namespace) -> int:
    setup = EvaluationSetup(
        detector=build_detector(settings),
        criteria=_build_criteria(settings),
        tracker_factory=lambda: _build_tracker(settings),
        stride_s=args.stride,
        sample_s=args.sample,
    )
    video = Path(args.evaluate)
    labels = load_labels(args.labels)
    if args.sweep is not None:
        print(format_sweep(sweep_area_ratio(video, labels, setup, args.sweep)))
    else:
        print(format_metrics(evaluate_video(video, labels, setup)))
    return EXIT_OK


def _build_tracker(settings: Settings) -> PresenceTracker:
    return PresenceTracker(present_after_s=settings.present_after_s, absent_after_s=settings.absent_after_s)


def _build_criteria(settings: Settings) -> PresenceCriteria:
    return PresenceCriteria(min_face_area_ratio=settings.min_face_area_ratio)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="study-presence", description="摄像头在座学习状态监测")
    parser.add_argument("--backend", choices=BACKENDS, help="检测后端，默认取 SP_BACKEND 或 local")
    parser.add_argument("--camera", type=int, metavar="INDEX", help="摄像头编号")
    parser.add_argument("--source", metavar="PATH", help="改用视频或图片文件作为输入（无摄像头时演示用）")
    parser.add_argument("--interval", type=float, metavar="SECONDS", help="检测间隔秒数")
    parser.add_argument(
        "--report",
        type=int,
        nargs="?",
        const=MIN_DAYS,
        metavar="DAYS",
        help="只打印近 DAYS 天在座时长后退出（默认 1 天，即今天）",
    )
    parser.add_argument("--csv", type=Path, metavar="PATH", help="与 --report 连用，同时导出 CSV")
    parser.add_argument("--evaluate", metavar="VIDEO", help="回放标注视频评估在座判定")
    parser.add_argument("--labels", type=Path, metavar="CSV", help="与 --evaluate 连用的标注文件")
    parser.add_argument(
        "--sweep",
        type=_parse_ratios,
        metavar="R1,R2,...",
        help="扫描最小人脸面积占比，输出阈值与指标曲线",
    )
    parser.add_argument(
        "--stride", type=float, default=DEFAULT_STRIDE_S, metavar="SECONDS", help="评估时的检测步长"
    )
    parser.add_argument(
        "--sample", type=float, default=DEFAULT_SAMPLE_S, metavar="SECONDS", help="评估时的采样步长"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    return parser


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.csv is not None and args.report is None:
        parser.error("--csv 需要与 --report 一起使用")
    if args.report is not None and args.report < MIN_DAYS:
        parser.error(f"--report 的天数必须 >= {MIN_DAYS}")
    if args.evaluate is not None and args.labels is None:
        parser.error("--evaluate 需要同时给 --labels")
    if args.labels is not None and args.evaluate is None:
        parser.error("--labels 只能与 --evaluate 一起使用")
    if args.sweep is not None and args.evaluate is None:
        parser.error("--sweep 只能与 --evaluate 一起使用")
    return args


def _parse_ratios(raw: str) -> list[float]:
    try:
        ratios = [float(piece) for piece in raw.split(RATIO_SEPARATOR) if piece.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"需要逗号分隔的数字：{raw!r}") from exc
    if not ratios:
        raise argparse.ArgumentTypeError("至少给一个阈值")
    return ratios


def _build_source(settings: Settings) -> FrameSource:
    if settings.source_path is not None:
        return VideoFileSource(settings.source_path)
    return CameraSource(settings.camera_index)


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    overrides: dict[str, object] = {}
    if args.backend is not None:
        overrides["backend"] = args.backend
    if args.camera is not None:
        overrides["camera_index"] = args.camera
    if args.source is not None:
        overrides["source_path"] = Path(args.source).expanduser()
    if args.interval is not None:
        overrides["detect_interval_s"] = args.interval
    return replace(settings, **overrides) if overrides else settings


if __name__ == "__main__":
    sys.exit(main())
