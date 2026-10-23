from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.presence.tracker import PresenceEvent, PresenceState, PresenceTracker

START = datetime(2026, 1, 1, 9, 0)


def at(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def build(present_after_s: float = 4.0, absent_after_s: float = 6.0) -> PresenceTracker:
    return PresenceTracker(present_after_s=present_after_s, absent_after_s=absent_after_s)


def test_occupancy_waits_for_full_window() -> None:
    tracker = build()
    assert tracker.update(occupied=True, active=False, now=at(0)) is None
    assert tracker.state is PresenceState.ABSENT
    assert tracker.update(occupied=True, active=False, now=at(3.9)) is None
    event = tracker.update(occupied=True, active=False, now=at(4.0))
    assert event == PresenceEvent(state=PresenceState.IDLE, changed_at=at(4.0))


def test_active_flips_immediately_and_returns_to_idle() -> None:
    tracker = build()
    tracker.update(occupied=True, active=False, now=at(0))
    tracker.update(occupied=True, active=False, now=at(4.0))
    assert tracker.update(occupied=True, active=True, now=at(5.0)) == PresenceEvent(
        state=PresenceState.ACTIVE, changed_at=at(5.0)
    )
    assert tracker.update(occupied=True, active=False, now=at(6.0)) == PresenceEvent(
        state=PresenceState.IDLE, changed_at=at(6.0)
    )


def test_absence_waits_for_full_window() -> None:
    tracker = build()
    tracker.update(occupied=True, active=False, now=at(0))
    tracker.update(occupied=True, active=False, now=at(4.0))
    assert tracker.update(occupied=False, active=False, now=at(10.0)) is None
    assert tracker.update(occupied=False, active=False, now=at(15.9)) is None
    assert tracker.update(occupied=False, active=False, now=at(16.0)) == PresenceEvent(
        state=PresenceState.ABSENT, changed_at=at(16.0)
    )


def test_short_gap_does_not_break_presence() -> None:
    tracker = build()
    tracker.update(occupied=True, active=False, now=at(0))
    tracker.update(occupied=True, active=False, now=at(4.0))
    tracker.update(occupied=False, active=False, now=at(5.0))
    tracker.update(occupied=True, active=False, now=at(7.0))
    assert tracker.state is PresenceState.IDLE


def test_flicker_restarts_pending_window() -> None:
    tracker = build()
    assert tracker.update(occupied=True, active=False, now=at(0)) is None
    assert tracker.update(occupied=False, active=False, now=at(2.0)) is None
    assert tracker.update(occupied=True, active=False, now=at(3.0)) is None
    assert tracker.update(occupied=True, active=False, now=at(6.9)) is None
    assert tracker.state is PresenceState.ABSENT
    assert tracker.update(occupied=True, active=False, now=at(7.0)) is not None


def test_no_event_when_state_stays() -> None:
    tracker = build()
    tracker.update(occupied=True, active=True, now=at(0))
    assert tracker.update(occupied=True, active=True, now=at(4.0)) is not None
    assert tracker.update(occupied=True, active=True, now=at(30.0)) is None


def test_initial_state_can_be_occupied() -> None:
    tracker = PresenceTracker(present_after_s=1.0, absent_after_s=1.0, initial=PresenceState.ACTIVE)
    assert tracker.state is PresenceState.ACTIVE
    assert tracker.update(occupied=True, active=True, now=at(0)) is None


@pytest.mark.parametrize(("present_after_s", "absent_after_s"), [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_non_positive_thresholds_rejected(present_after_s: float, absent_after_s: float) -> None:
    with pytest.raises(ValueError, match="阈值"):
        PresenceTracker(present_after_s=present_after_s, absent_after_s=absent_after_s)
