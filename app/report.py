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
CSV_HEADER: Final[tuple[str, ...]] = (
    "date",
    "present_seconds",
    "active_seconds",
    "present_duration",
    "active_duration",
)
SECONDS_PRECISION: Final[int] = 3
ACTIVE_STATE: Final[str] = "active"


@dataclass(frozen=True, slots=True)
class DayTotal:
    day: date
    present_seconds: float
    active_seconds: float


def report_window(days: int, now: datetime) -> tuple[datetime, datetime]:
    """返回 [起始日 00:00, now]；days=1 即今天。"""
    if days < MIN_DAYS:
        raise ValueError("天数必须 >= 1")
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days - MIN_DAYS), now


def daily_totals(
    sessions: Sequence[SessionRecord], window_start: datetime, window_end: datetime
) -> list[DayTotal]:
    """逐日累加：在座时长含全部区间，有交互时长只算 active 区间。"""
    totals: list[DayTotal] = []
    day_start = window_start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day_start < window_end:
        day_end = day_start + timedelta(days=1)
        lower = max(day_start, window_start)
        upper = min(day_end, window_end)
        totals.append(
            DayTotal(
                day=day_start.date(),
                present_seconds=_sum_overlap(sessions, (lower, upper), window_end),
                active_seconds=_sum_overlap(sessions, (lower, upper), window_end, state=ACTIVE_STATE),
            )
        )
        day_start = day_end
    return totals


def render_text(totals: Sequence[DayTotal]) -> str:
    lines = [f"在座 / 有交互时长（近 {len(totals)} 天）"]
    lines.extend(
        f"{total.day.isoformat()}  在座 {format_duration(total.present_seconds)}"
        f"  有交互 {format_duration(total.active_seconds)}"
        for total in totals
    )
    present = sum(total.present_seconds for total in totals)
    active = sum(total.active_seconds for total in totals)
    active_days = sum(1 for total in totals if total.present_seconds > 0)
    lines.append(f"合计: 在座 {format_duration(present)}  有交互 {format_duration(active)}")
    if active_days:
        lines.append(f"有记录: {active_days} 天，日均在座 {format_duration(present / active_days)}")
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
                    round(total.present_seconds, SECONDS_PRECISION),
                    round(total.active_seconds, SECONDS_PRECISION),
                    format_duration(total.present_seconds),
                    format_duration(total.active_seconds),
                ]
            )
    logger.info("CSV 已写入：%s", path)


def _sum_overlap(
    sessions: Sequence[SessionRecord],
    span: tuple[datetime, datetime],
    window_end: datetime,
    *,
    state: str | None = None,
) -> float:
    lower, upper = span
    return sum(
        overlap_seconds(record.started_at, record.ended_at or window_end, lower, upper)
        for record in sessions
        if state is None or record.state == state
    )
