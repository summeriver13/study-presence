"""交互证据来源：系统级「距离上次键鼠输入多少秒」。

只读取空闲时长，不读取按键内容、不记录输入历史；不支持的平台返回 None，
判定退化为纯视觉（此时在座即视为有交互，并在界面上标注「交互检测不可用」）。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Final, Protocol, runtime_checkable

MILLISECONDS_PER_SECOND: Final[float] = 1000.0
_UINT32_MASK: Final[int] = 0xFFFFFFFF

logger = logging.getLogger(__name__)


@runtime_checkable
class ActivitySource(Protocol):
    available: bool

    def idle_seconds(self) -> float | None: ...


class NullActivitySource:
    """平台不支持或用户关闭时的空实现。"""

    available = False

    def idle_seconds(self) -> float | None:
        return None


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]


class WindowsActivitySource:
    """user32!GetLastInputInfo：返回自上次输入以来的毫秒数。"""

    available = True

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    def idle_seconds(self) -> float | None:
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(_LastInputInfo)
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        now_ms = self._kernel32.GetTickCount() & _UINT32_MASK
        elapsed_ms = (now_ms - info.dwTime) & _UINT32_MASK
        return elapsed_ms / MILLISECONDS_PER_SECOND


def build_activity_source(enabled: bool) -> ActivitySource:
    if not enabled:
        logger.info("交互检测已关闭（SP_TRACK_INPUT=0），仅在座判定生效")
        return NullActivitySource()
    if sys.platform != "win32":
        logger.info("当前平台（%s）不支持键鼠空闲检测，交互判定退化为纯视觉", sys.platform)
        return NullActivitySource()
    return WindowsActivitySource()
