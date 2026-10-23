"""纯展示格式化：不依赖 Tk，便于单独测试。"""

from __future__ import annotations

from typing import Final

HOURS_PER_SECOND: Final[float] = 3600.0
MINUTES_PER_SECOND: Final[float] = 60.0


def format_duration(total_seconds: float) -> str:
    """秒数转 HH:MM:SS；负数按 0 处理。"""
    seconds = max(0, int(total_seconds))
    hours, remainder = divmod(seconds, int(HOURS_PER_SECOND))
    minutes, secs = divmod(remainder, int(MINUTES_PER_SECOND))
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
