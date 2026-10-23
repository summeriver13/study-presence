"""python -m app / study-presence：解析参数、装配依赖、启动窗口。"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Final

from app.camera import CameraSource
from app.config.settings import BACKENDS, ConfigError, Settings
from app.detectors import build_detector
from app.detectors.base import DetectorError
from app.pipeline import DEFAULT_DISPLAY_HEIGHT, DEFAULT_DISPLAY_WIDTH, PresenceMonitor
from app.presence.store import PresenceStore
from app.presence.tracker import PresenceTracker
from app.sources import FrameSource, SourceError, VideoFileSource
from app.ui.window import StudyPresenceWindow

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
EXIT_OK: Final[int] = 0
EXIT_FAILURE: Final[int] = 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        settings = _apply_overrides(Settings.from_env(), args)
        detector = build_detector(settings)
        source = _build_source(settings)
        source.open()
        store = PresenceStore(settings.db_path)
    except (ConfigError, SourceError, DetectorError) as exc:
        logging.error("%s", exc)
        return EXIT_FAILURE

    monitor = PresenceMonitor(
        source=source,
        detector=detector,
        tracker=PresenceTracker(present_after=settings.present_after, absent_after=settings.absent_after),
        store=store,
        detect_interval_s=settings.detect_interval_s,
        display_width=DEFAULT_DISPLAY_WIDTH,
        display_height=DEFAULT_DISPLAY_HEIGHT,
    )
    try:
        StudyPresenceWindow(
            monitor, display_width=DEFAULT_DISPLAY_WIDTH, display_height=DEFAULT_DISPLAY_HEIGHT
        ).run()
    finally:
        source.close()
        store.close()
    return EXIT_OK


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="study-presence", description="摄像头在座学习状态监测")
    parser.add_argument("--backend", choices=BACKENDS, help="检测后端，默认取 SP_BACKEND 或 local")
    parser.add_argument("--camera", type=int, metavar="INDEX", help="摄像头编号")
    parser.add_argument("--source", metavar="PATH", help="改用视频或图片文件作为输入（无摄像头时演示用）")
    parser.add_argument("--interval", type=float, metavar="SECONDS", help="检测间隔秒数")
    return parser.parse_args(argv)


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
