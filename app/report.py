"""在座时长报表：把会话区间按天切分，输出文本表格与 CSV。"""

from __future__ import annotations

import csv
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final

from app.presence.store import SessionRecord, overlap_seconds
from app.ui.format import format_duration

logger = logging.getLogger(__name__)

MIN_DAYS: Final[int] = 1
CSV_HEADER: Final[tuple[str, ...]] = ("date", "seconds", "duration")
SECONDS_PRECISION: Final[int] = 3


@dataclass(frozen=True, slots=True)
class DayTotal:
    day: date
    seconds: float


def report_window(days: int, now: datetime) -> tuple[datetime, datetime]:
    """返回 [起始日 00:00, now]；days=1 即今天。"""
    if days < MIN_DAYS:
        raise ValueError("天数必须 >= 1")
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days - MIN_DAYS), now


def daily_totals(
    sessions: Sequence[SessionRecord], window_start: datetime, window_end: datetime
) -> list[DayTotal]:
    """逐日累加，未结束的会话截到 window_end；无记录的日子补 0。"""
    totals: list[DayTotal] = []
    day_start = window_start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day_start < window_end:
        day_end = day_start + timedelta(days=1)
        lower = max(day_start, window_start)
        upper = min(day_end, window_end)
        seconds = sum(
            overlap_seconds(record.started_at, record.ended_at or window_end, lower, upper)
            for record in sessions
        )
        totals.append(DayTotal(day=day_start.date(), seconds=seconds))
        day_start = day_end
    return totals


def render_text(totals: Sequence[DayTotal]) -> str:
    lines = [f"在座时长（近 {len(totals)} 天）"]
    lines.extend(f"{total.day.isoformat()}  {format_duration(total.seconds)}" for total in totals)
    total_seconds = sum(total.seconds for total in totals)
    active_days = sum(1 for total in totals if total.seconds > 0)
    lines.append(f"合计: {format_duration(total_seconds)}")
    if active_days:
        average = total_seconds / active_days
        lines.append(f"有记录: {active_days} 天，日均 {format_duration(average)}")
    return "\n".join(lines)


def write_csv(totals: Sequence[DayTotal], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for total in totals:
            writer.writerow(
                [
                    total.day.isoformat(),
                    round(total.seconds, SECONDS_PRECISION),
                    format_duration(total.seconds),
                ]
            )
    logger.info("CSV 已写入：%s", path)
