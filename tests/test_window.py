from __future__ import annotations

import pytest

from app.ui.window import format_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0.0, "00:00:00"), (59.9, "00:00:59"), (61.0, "00:01:01"), (3661.0, "01:01:01"), (-5.0, "00:00:00")],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert format_duration(seconds) == expected
