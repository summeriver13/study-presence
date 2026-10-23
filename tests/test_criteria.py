from __future__ import annotations

import pytest

from app.detectors.base import DetectionResult, FaceBox
from app.presence.criteria import PresenceCriteria


def face(x: float, y: float, width: float = 0.2, height: float = 0.3) -> FaceBox:
    return FaceBox(x=x, y=y, width=width, height=height)


@pytest.fixture
def criteria() -> PresenceCriteria:
    return PresenceCriteria()


def test_face_in_center_is_qualified(criteria: PresenceCriteria) -> None:
    assert criteria.occupied(DetectionResult((face(0.4, 0.3),)))


def test_face_at_edge_is_rejected(criteria: PresenceCriteria) -> None:
    assert not criteria.occupied(DetectionResult((face(0.0, 0.3),)))
    assert not criteria.occupied(DetectionResult((face(0.85, 0.3),)))


def test_tiny_face_is_rejected(criteria: PresenceCriteria) -> None:
    assert not criteria.occupied(DetectionResult((face(0.45, 0.45, width=0.05, height=0.05),)))


def test_one_qualified_face_is_enough(criteria: PresenceCriteria) -> None:
    result = DetectionResult((face(0.0, 0.0, 0.05, 0.05), face(0.45, 0.45)))
    assert len(criteria.qualified_faces(result)) == 1


def test_no_faces_is_not_occupied(criteria: PresenceCriteria) -> None:
    assert not criteria.occupied(DetectionResult())


def test_area_ratio_and_center_properties() -> None:
    box = face(0.2, 0.4, width=0.4, height=0.5)
    assert box.area_ratio == pytest.approx(0.2)
    assert box.center == pytest.approx((0.4, 0.65))


def test_threshold_is_configurable() -> None:
    lenient = PresenceCriteria(min_face_area_ratio=0.001)
    assert lenient.occupied(DetectionResult((face(0.45, 0.45, width=0.05, height=0.05),)))
