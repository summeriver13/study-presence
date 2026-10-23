from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.presence.store import SessionRecord
from app.report import daily_totals, render_text, report_window, write_csv

NOW = datetime(2026, 3, 10, 20, 0)
ACTIVE = "active"
IDLE = "idle"


def record(started_offset_h: float, duration_h: float, state: str = ACTIVE) -> SessionRecord:
    started = NOW - timedelta(hours=started_offset_h)
    return SessionRecord(
        backend="local:yunet",
        state=state,
        started_at=started,
        ended_at=started + timedelta(hours=duration_h),
    )


def test_window_covers_whole_days_up_to_now() -> None:
    start, end = report_window(7, NOW)
    assert start == datetime(2026, 3, 4, 0, 0)
    assert end == NOW


def test_window_rejects_non_positive_days() -> None:
    with pytest.raises(ValueError, match="天数"):
        report_window(0, NOW)


def test_today_only_counts_today() -> None:
    totals = daily_totals([record(1.0, 0.5)], *report_window(1, NOW))
    assert [total.day.isoformat() for total in totals] == ["2026-03-10"]
    assert totals[0].present_seconds == pytest.approx(1800.0)
    assert totals[0].active_seconds == pytest.approx(1800.0)


def test_idle_time_counts_as_present_but_not_active() -> None:
    totals = daily_totals([record(1.0, 1.0, state=IDLE)], *report_window(1, NOW))
    assert totals[0].present_seconds == pytest.approx(3600.0)
    assert totals[0].active_seconds == pytest.approx(0.0)


def test_session_spanning_midnight_is_split() -> None:
    totals = daily_totals([record(22.0, 4.0)], *report_window(2, NOW))
    assert [round(total.present_seconds) for total in totals] == [7200, 7200]


def test_open_session_is_clipped_to_now() -> None:
    open_session = SessionRecord(
        backend="local:yunet", state=ACTIVE, started_at=NOW - timedelta(minutes=30), ended_at=None
    )
    totals = daily_totals([open_session], *report_window(1, NOW))
    assert totals[0].present_seconds == pytest.approx(1800.0)


def test_empty_days_are_zero_filled() -> None:
    totals = daily_totals([], *report_window(3, NOW))
    assert [total.present_seconds for total in totals] == [0.0, 0.0, 0.0]


def test_render_text_includes_total_and_average() -> None:
    totals = daily_totals([record(1.0, 1.0), record(25.0, 3.0, state=IDLE)], *report_window(2, NOW))
    text = render_text(totals)
    assert "合计: 在座 04:00:00  有交互 01:00:00" in text
    assert "有记录: 2 天，日均在座 02:00:00" in text


def test_write_csv_has_header_and_rows(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "week.csv"
    write_csv(daily_totals([record(1.0, 1.0)], *report_window(1, NOW)), path)
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["date", "present_seconds", "active_seconds", "present_duration", "active_duration"]
    assert rows[1] == ["2026-03-10", "3600.0", "3600.0", "01:00:00", "01:00:00"]
