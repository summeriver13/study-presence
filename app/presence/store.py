"""SQLite 会话存储：记录每段在座状态区间，支撑在座时长与有交互时长。

时间一律按本地时间存储（naive），带时区的入参先转换成本地 naive。
旧库（无 state 列）在打开时自动补列，历史记录按 active 处理。
连接允许跨线程使用（check_same_thread=False），内部加锁串行化，UI 不直接访问。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_started_at ON session (started_at);
"""
STATE_COLUMN: Final[str] = "state"
ADD_STATE_COLUMN: Final[str] = "ALTER TABLE session ADD COLUMN state TEXT NOT NULL DEFAULT 'active'"


@dataclass(frozen=True, slots=True)
class SessionRecord:
    backend: str
    state: str
    started_at: datetime
    ended_at: datetime | None


class PresenceStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.executescript(SCHEMA)
        self._connection.commit()
        self._migrate()
        logger.debug("打开数据库：%s", path)

    def close(self) -> None:
        with self._lock:
            self._connection.close()
        logger.debug("关闭数据库")

    def start_session(self, backend: str, state: str, started_at: datetime) -> int:
        moment = _as_local_naive(started_at)
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO session (backend, state, started_at) VALUES (?, ?, ?)",
                (backend, state, moment.isoformat()),
            )
            self._connection.commit()
        session_id = int(cursor.lastrowid or 0)
        logger.debug("开启会话 %d（%s）：%s", session_id, state, moment.isoformat(timespec="seconds"))
        return session_id

    def end_session(self, session_id: int, ended_at: datetime) -> None:
        moment = _as_local_naive(ended_at)
        with self._lock:
            self._connection.execute(
                "UPDATE session SET ended_at = ? WHERE id = ?",
                (moment.isoformat(), session_id),
            )
            self._connection.commit()
        logger.debug("结束会话 %d：%s", session_id, moment.isoformat(timespec="seconds"))

    def sessions_between(self, window_start: datetime, window_end: datetime) -> list[SessionRecord]:
        """窗口内与会话相交的记录；未结束的会话原样返回，由调用方决定裁剪终点。"""
        start = _as_local_naive(window_start)
        end = _as_local_naive(window_end)
        with self._lock:
            rows = self._connection.execute(
                "SELECT backend, state, started_at, ended_at FROM session "
                "WHERE (ended_at IS NULL OR ended_at >= ?) AND started_at <= ? ORDER BY started_at",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            SessionRecord(
                backend=str(backend),
                state=str(state),
                started_at=datetime.fromisoformat(started_raw),
                ended_at=datetime.fromisoformat(ended_raw) if ended_raw else None,
            )
            for backend, state, started_raw, ended_raw in rows
        ]

    def seconds_between(
        self, window_start: datetime, window_end: datetime, *, state: str | None = None
    ) -> float:
        """窗口内累计秒数：state 为空时统计全部在座区间，否则只统计该状态的区间。"""
        start = _as_local_naive(window_start)
        end = _as_local_naive(window_end)
        records = self.sessions_between(start, end)
        if state is not None:
            records = [record for record in records if record.state == state]
        return sum(
            overlap_seconds(record.started_at, record.ended_at or end, start, end) for record in records
        )

    def _migrate(self) -> None:
        with self._lock:
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(session)")}
            if STATE_COLUMN in columns:
                return
            self._connection.execute(ADD_STATE_COLUMN)
            self._connection.commit()
        logger.info("旧数据库已补 state 列，历史记录按 active 统计")


def overlap_seconds(
    started: datetime, ended: datetime, window_start: datetime, window_end: datetime
) -> float:
    """[started, ended) 与窗口的交集秒数，无交集返回 0。"""
    lower = max(started, window_start)
    upper = min(ended, window_end)
    return max(0.0, (upper - lower).total_seconds())


def _as_local_naive(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone().replace(tzinfo=None)
