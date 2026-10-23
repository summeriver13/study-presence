"""SQLite 会话存储：记录每次在座区间，支撑「今日在座时长」。

时间一律按本地时间存储（naive），带时区的入参先转换成本地 naive。
连接允许跨线程使用（check_same_thread=False），内部加锁串行化，UI 不直接访问。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Final

SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_started_at ON session (started_at);
"""


class PresenceStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def start_session(self, backend: str, started_at: datetime) -> int:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO session (backend, started_at) VALUES (?, ?)",
                (backend, _as_local_naive(started_at).isoformat()),
            )
            self._connection.commit()
        return int(cursor.lastrowid or 0)

    def end_session(self, session_id: int, ended_at: datetime) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE session SET ended_at = ? WHERE id = ?",
                (_as_local_naive(ended_at).isoformat(), session_id),
            )
            self._connection.commit()

    def seconds_between(self, window_start: datetime, window_end: datetime) -> float:
        """窗口内累计在座秒数：未结束的会话截到 window_end，跨窗口的会话被裁剪。"""
        window_start = _as_local_naive(window_start)
        window_end = _as_local_naive(window_end)
        with self._lock:
            rows = self._connection.execute(
                "SELECT started_at, ended_at FROM session WHERE ended_at IS NULL OR ended_at >= ?",
                (window_start.isoformat(),),
            ).fetchall()
        total = 0.0
        for started_raw, ended_raw in rows:
            started = datetime.fromisoformat(started_raw)
            ended = datetime.fromisoformat(ended_raw) if ended_raw else window_end
            total += _overlap_seconds(started, ended, window_start, window_end)
        return total


def _as_local_naive(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone().replace(tzinfo=None)


def _overlap_seconds(
    started: datetime, ended: datetime, window_start: datetime, window_end: datetime
) -> float:
    lower = max(started, window_start)
    upper = min(ended, window_end)
    return max(0.0, (upper - lower).total_seconds())
