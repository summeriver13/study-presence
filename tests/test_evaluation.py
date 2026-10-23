from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation import Metrics, Span, compare, format_metrics, format_sweep, load_labels


def span(start_s: float, end_s: float, present: bool = True) -> Span:
    return Span(start_s=start_s, end_s=end_s, present=present)


def test_load_labels_parses_states(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("start_s,end_s,label\n0,10,absent\n10,20,idle\n20,30,active\n", encoding="utf-8")
    spans = load_labels(path)
    assert [item.present for item in spans] == [False, True, True]


def test_load_labels_rejects_unknown_label(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("start_s,end_s,label\n0,10,studying\n", encoding="utf-8")
    with pytest.raises(ValueError, match="未知标注"):
        load_labels(path)


def test_perfect_prediction_has_no_errors() -> None:
    truth = [span(0, 10, False), span(10, 20, True)]
    metrics = compare(truth, truth, sample_s=1.0)
    assert metrics.false_positive == 0
    assert metrics.false_negative == 0
    assert metrics.f1 == pytest.approx(1.0)


def test_false_positive_when_predicted_present_outside_truth() -> None:
    truth = [span(0, 10, False), span(10, 20, True)]
    predicted = [span(0, 20, True)]
    metrics = compare(predicted, truth, sample_s=1.0)
    assert metrics.true_positive == 10
    assert metrics.false_positive == 10
    assert metrics.false_negative == 0


def test_false_negative_when_truth_present_but_predicted_absent() -> None:
    truth = [span(0, 10, True), span(10, 20, False)]
    predicted = [span(0, 5, True)]
    metrics = compare(predicted, truth, sample_s=1.0)
    assert metrics.true_positive == 5
    assert metrics.false_negative == 5
    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(0.5)


def test_metrics_with_no_positive_prediction_do_not_divide_by_zero() -> None:
    metrics = Metrics(true_positive=0, false_positive=0, true_negative=3, false_negative=2)
    assert metrics.precision == pytest.approx(0.0)
    assert metrics.recall == pytest.approx(0.0)
    assert metrics.f1 == pytest.approx(0.0)
    assert metrics.accuracy == pytest.approx(0.6)


def test_sample_step_must_be_positive() -> None:
    with pytest.raises(ValueError, match="sample_s"):
        compare([span(0, 1)], [span(0, 1)], sample_s=0.0)


def test_formatters_produce_readable_output() -> None:
    metrics = Metrics(true_positive=4, false_positive=1, true_negative=3, false_negative=2)
    assert "precision" in format_metrics(metrics)
    assert "占比" in format_sweep([(0.02, metrics)])
