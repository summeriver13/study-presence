"""Tkinter 窗口：主线程只渲染与响应事件，采集/检测在 worker 线程。"""

from __future__ import annotations

import queue
import tkinter as tk
import tkinter.font as tkfont
from typing import Final, cast

from PIL import Image, ImageTk

from app.pipeline import FrameUpdate, PresenceMonitor, StatusUpdate
from app.presence.tracker import PresenceState
from app.ui.format import format_duration

WINDOW_TITLE: Final[str] = "study-presence · 在座学习监测"
CANVAS_BG: Final[str] = "#0d1117"
TEXT_COLOR: Final[str] = "#e6edf3"
MUTED_COLOR: Final[str] = "#8b949e"
PRESENT_COLOR: Final[str] = "#3fb950"
ABSENT_COLOR: Final[str] = "#8b949e"
ERROR_COLOR: Final[str] = "#d29922"
REFRESH_MS: Final[int] = 33
LARGE_FONT_SIZE: Final[int] = 20
SMALL_FONT_SIZE: Final[int] = 10
FONT_CANDIDATES: Final[tuple[str, ...]] = (
    "Microsoft YaHei UI",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Segoe UI",
)


class StudyPresenceWindow:
    def __init__(
        self,
        monitor: PresenceMonitor,
        *,
        display_width: int = 640,
        display_height: int = 360,
    ) -> None:
        self._monitor = monitor
        self._display_size = (display_width, display_height)
        self._photo: ImageTk.PhotoImage | None = None
        self._canvas_item: int | None = None
        self._root = tk.Tk()
        self._root.title(WINDOW_TITLE)
        self._root.configure(bg=CANVAS_BG)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        family = _pick_font(self._root)
        self._canvas = self._build_canvas()
        self._state_label = self._build_state_label(family)
        self._detail_label = self._build_detail_label(family)
        self._error_label = self._build_error_label(family)

    def run(self) -> None:
        self._monitor.start()
        try:
            self._root.after(REFRESH_MS, self._pump)
            self._root.mainloop()
        finally:
            self._monitor.stop()

    def _build_canvas(self) -> tk.Canvas:
        width, height = self._display_size
        canvas = tk.Canvas(self._root, width=width, height=height, bg=CANVAS_BG, highlightthickness=0)
        canvas.pack(padx=16, pady=(16, 8))
        return canvas

    def _build_state_label(self, family: str) -> tk.Label:
        label = tk.Label(
            self._root,
            text="等待画面…",
            font=(family, LARGE_FONT_SIZE, "bold"),
            fg=ABSENT_COLOR,
            bg=CANVAS_BG,
        )
        label.pack(pady=(0, 4))
        return label

    def _build_detail_label(self, family: str) -> tk.Label:
        label = tk.Label(self._root, text="", font=(family, SMALL_FONT_SIZE), fg=MUTED_COLOR, bg=CANVAS_BG)
        label.pack()
        return label

    def _build_error_label(self, family: str) -> tk.Label:
        label = tk.Label(self._root, text="", font=(family, SMALL_FONT_SIZE), fg=ERROR_COLOR, bg=CANVAS_BG)
        label.pack(pady=(4, 12))
        return label

    def _pump(self) -> None:
        self._render_frame()
        self._render_statuses()
        self._root.after(REFRESH_MS, self._pump)

    def _render_frame(self) -> None:
        update = _drain_last(self._monitor.frames)
        if update is None:
            return
        width, height = self._display_size
        self._photo = ImageTk.PhotoImage(Image.fromarray(update.rgb))
        if self._canvas_item is None:
            self._canvas_item = self._canvas.create_image(width // 2, height // 2, image=self._photo)
            return
        self._canvas.itemconfigure(self._canvas_item, image=self._photo)

    def _render_statuses(self) -> None:
        status = _drain_last(self._monitor.statuses)
        if status is None:
            return
        self._apply_status(status)

    def _apply_status(self, status: StatusUpdate) -> None:
        present = status.state is PresenceState.PRESENT
        self._state_label.configure(
            text="在座学习中" if present else "暂无人在座",
            fg=PRESENT_COLOR if present else ABSENT_COLOR,
        )
        faces = "—" if status.face_count is None else str(status.face_count)
        duration = format_duration(status.present_seconds_today)
        parts = [f"今日在座 {duration}", f"人脸 {faces}", f"后端 {status.backend}"]
        if status.detect_ms is not None:
            parts.append(f"检测 {status.detect_ms:.0f} ms")
        self._detail_label.configure(text="　".join(parts))
        self._error_label.configure(text=status.error or "")

    def _on_close(self) -> None:
        self._monitor.stop()
        self._root.destroy()


def _drain_last[UpdateT: (FrameUpdate, StatusUpdate)](target: queue.Queue[UpdateT]) -> UpdateT | None:
    latest: UpdateT | None = None
    while True:
        try:
            latest = target.get_nowait()
        except queue.Empty:
            return latest


def _pick_font(root: tk.Tk) -> str:
    available = set(tkfont.families(root))
    for name in FONT_CANDIDATES:
        if name in available:
            return name
    default = tkfont.nametofont("TkDefaultFont").actual()
    return cast(str, default["family"])
