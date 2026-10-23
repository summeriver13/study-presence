"""python -m app / study-presence：解析参数、装配依赖，启动窗口或打印报表。"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Final

from app.camera import CameraSource
from app.config.settings import BACKENDS, ConfigError, Settings
from app.detectors import build_detector
from app.detectors.base import DetectorError
from app.pipeline import DEFAULT_DISPLAY_HEIGHT, DEFAULT_DISPLAY_WIDTH, PresenceMonitor
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceTracker
from app.report import MIN_DAYS, daily_totals, render_text, report_window, write_csv
from app.sources import FrameSource, SourceError, VideoFileSource
from app.ui.window import StudyPresenceWindow

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
EXIT_OK: Final[int] = 0
EXIT_FAILURE: Final[int] = 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=LOG_FORMAT)
    try:
        settings = _apply_overrides(Settings.from_env(), args)
        if args.report is not None:
            return _run_report(settings, days=args.report, csv_path=args.csv)
        return _run_window(settings)
    except (ConfigError, SourceError, DetectorError) as exc:
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
            tracker=PresenceTracker(present_after=settings.present_after, absent_after=settings.absent_after),
            store=store,
            detect_interval_s=settings.detect_interval_s,
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
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    return parser


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.csv is not None and args.report is None:
        parser.error("--csv 需要与 --report 一起使用")
    if args.report is not None and args.report < MIN_DAYS:
        parser.error(f"--report 的天数必须 >= {MIN_DAYS}")
    return args


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
