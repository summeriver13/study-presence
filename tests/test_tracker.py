from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.presence.tracker import PresenceEvent, PresenceState, PresenceTracker

BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


def test_starts_absent_and_ignores_single_observation() -> None:
    tracker = PresenceTracker()
    assert tracker.state is PresenceState.ABSENT
    assert tracker.update(1, at(0)) is None
    assert tracker.state is PresenceState.ABSENT


def test_switches_to_present_after_threshold() -> None:
    tracker = PresenceTracker(present_after=2)
    tracker.update(1, at(0))
    event = tracker.update(1, at(1))
    assert event == PresenceEvent(state=PresenceState.PRESENT, changed_at=at(1))


def test_absent_observation_resets_streak() -> None:
    tracker = PresenceTracker(present_after=2)
    tracker.update(1, at(0))
    tracker.update(0, at(1))
    assert tracker.update(1, at(2)) is None
    assert tracker.state is PresenceState.ABSENT


def test_switches_back_to_absent_after_threshold() -> None:
    tracker = PresenceTracker(present_after=1, absent_after=3)
    tracker.update(1, at(0))
    assert tracker.update(0, at(1)) is None
    assert tracker.update(0, at(2)) is None
    event = tracker.update(0, at(3))
    assert event is not None
    assert event.state is PresenceState.ABSENT
    assert event.changed_at == at(3)


def test_no_event_while_state_stable() -> None:
    tracker = PresenceTracker(present_after=1)
    tracker.update(1, at(0))
    for tick in range(1, 5):
        assert tracker.update(1, at(tick)) is None


def test_recovers_after_false_negative() -> None:
    tracker = PresenceTracker(present_after=1, absent_after=5)
    tracker.update(1, at(0))
    tracker.update(0, at(1))
    event = tracker.update(2, at(2))
    assert event is None
    assert tracker.state is PresenceState.PRESENT


@pytest.mark.parametrize(("present_after", "absent_after"), [(0, 3), (2, 0)])
def test_rejects_non_positive_thresholds(present_after: int, absent_after: int) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        PresenceTracker(present_after=present_after, absent_after=absent_after)
