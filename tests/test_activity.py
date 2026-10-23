from __future__ import annotations

import sys

import pytest

from app import activity
from app.activity import NullActivitySource, WindowsActivitySource, build_activity_source


def test_null_source_reports_unavailable() -> None:
    source = NullActivitySource()
    assert not source.available
    assert source.idle_seconds() is None


def test_disabled_tracking_returns_null_source() -> None:
    assert isinstance(build_activity_source(False), NullActivitySource)


def test_unsupported_platform_returns_null_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity.sys, "platform", "linux")
    assert isinstance(build_activity_source(True), NullActivitySource)


def test_windows_source_reads_idle_seconds() -> None:
    if sys.platform != "win32":
        pytest.skip("仅在 Windows 上验证 GetLastInputInfo")
    source = build_activity_source(True)
    assert isinstance(source, WindowsActivitySource)
    assert source.available
    idle = source.idle_seconds()
    assert idle is not None
    assert idle >= 0.0
