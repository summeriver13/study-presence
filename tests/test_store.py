from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.presence.store import PresenceStore

BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[PresenceStore]:
    store = PresenceStore(tmp_path / "nested" / "presence.db")
    yield store
    store.close()


def test_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "presence.db"
    store = PresenceStore(path)
    store.close()
    assert path.is_file()


def test_closed_session_is_counted(store: PresenceStore) -> None:
    session_id = store.start_session("local:yunet", at(0))
    store.end_session(session_id, at(60))
    assert store.seconds_between(at(0), at(120)) == pytest.approx(60.0)


def test_open_session_is_clipped_to_window_end(store: PresenceStore) -> None:
    store.start_session("local:yunet", at(0))
    assert store.seconds_between(at(0), at(30)) == pytest.approx(30.0)


def test_window_clips_session_on_both_sides(store: PresenceStore) -> None:
    session_id = store.start_session("local:yunet", at(0))
    store.end_session(session_id, at(100))
    assert store.seconds_between(at(20), at(50)) == pytest.approx(30.0)


def test_sessions_before_window_are_ignored(store: PresenceStore) -> None:
    session_id = store.start_session("local:yunet", at(0))
    store.end_session(session_id, at(10))
    assert store.seconds_between(at(60), at(120)) == pytest.approx(0.0)


def test_multiple_sessions_are_summed(store: PresenceStore) -> None:
    first = store.start_session("local:yunet", at(0))
    store.end_session(first, at(10))
    second = store.start_session("baidu:detect", at(20))
    store.end_session(second, at(40))
    assert store.seconds_between(at(0), at(60)) == pytest.approx(30.0)
