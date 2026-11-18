"""M2/M4 self-check. Run: python -m pytest -q -m student -o addopts= -k lab9"""
import csv
import math
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
TONE = Path("data/eval/judge_tone_public.csv")


@pytest.fixture(scope="module")
def stats():
    # The overlaid Lab 8 CI collects these tests with only Lab 8 dependencies.
    from lab9 import stats

    return stats


def _labels():
    rows = list(csv.DictReader(TONE.open(encoding="utf-8")))
    return [r["human"] for r in rows], [r["judge"] for r in rows]


def test_confusion_tone(stats):
    assert stats.confusion(*_labels()) == {"tp": 24, "fp": 4, "fn": 6, "tn": 66}


def test_precision_recall_kappa_tone(stats):
    p, r = stats.precision_recall(*_labels())
    assert (round(p, 3), round(r, 3)) == (0.857, 0.8)
    assert round(stats.cohen_kappa(*_labels()), 3) == 0.757


def test_kappa_undefined_for_constant_judge(stats):
    with pytest.raises(ValueError):
        stats.cohen_kappa(["PASS"] * 5, ["PASS"] * 5)


def test_rogan_gladen_clips(stats):
    assert stats.rogan_gladen(0.28, 0.8, 66 / 70) == pytest.approx(0.3, abs=0.01)
    assert stats.rogan_gladen(0.0, 0.8, 0.9) == 0.0


@pytest.mark.parametrize("human,judge", [([], []), (["PASS"], []), (["OTHER"], ["PASS"])])
def test_confusion_rejects_invalid_labels(stats, human, judge):
    with pytest.raises(ValueError):
        stats.confusion(human, judge)


def test_precision_recall_zero_denominators(stats):
    assert stats.precision_recall(["PASS"], ["PASS"]) == (0.0, 0.0)
    assert stats.precision_recall(["FAIL"], ["PASS"]) == (0.0, 0.0)


def test_kappa_constant_prediction_has_no_agreement_beyond_chance(stats):
    assert stats.cohen_kappa(["FAIL", "PASS"], ["PASS", "PASS"]) == 0.0


@pytest.mark.parametrize("rates", [(0.2, 0.5, 0.5), (0.2, 0.3, 0.4),
                                  (-0.1, 0.8, 0.9), (0.2, float("nan"), 0.9)])
def test_rogan_gladen_rejects_unusable_rates(stats, rates):
    with pytest.raises(ValueError):
        stats.rogan_gladen(*rates)


def test_rogan_gladen_clips_upper_bound(stats):
    assert stats.rogan_gladen(1.0, 0.8, 0.9) == 1.0


def test_judge_calibration_accepts_tone_and_rejects_helpful():
    from lab9.judge import calibrate

    tone = calibrate(TONE)
    helpful = calibrate(Path("data/eval/judge_helpful_public.csv"))
    assert tone["passed"] is True
    assert helpful["passed"] is False
    assert helpful["recall"] < 0.7


def test_judge_constant_labels_fail_calibration_without_crashing(tmp_path, capsys):
    from lab9.judge import calibrate, main

    path = tmp_path / "constant.csv"
    path.write_text("item_id,reply,human,judge\nT-001,ok,PASS,PASS\n", encoding="utf-8")
    result = calibrate(path)
    assert result["passed"] is False
    assert math.isnan(result["kappa"])
    assert math.isnan(result["corrected_fail_rate"])
    assert main(["--csv", str(path)]) == 1
    assert "FAIL floors" in capsys.readouterr().out


def test_paired_bootstrap_reference(stats):
    d, lo, hi = stats.paired_bootstrap([1, 1, 0.8, 1, 0.6], [1, 0.8, 0.8, 0.6, 0.6])
    assert d == pytest.approx(0.12, abs=1e-9)
    assert lo == pytest.approx(0.0, abs=0.01) and hi == pytest.approx(0.28, abs=0.01)


def test_paired_bootstrap_identical_is_zero(stats):
    assert stats.paired_bootstrap([1, 0, 1], [1, 0, 1]) == (0.0, 0.0, 0.0)


def test_paired_bootstrap_preserves_pairs(stats):
    result = stats.paired_bootstrap([0.2, 0.6, 1.0], [0.0, 0.4, 0.8])
    assert result == pytest.approx((0.2, 0.2, 0.2))


def test_paired_bootstrap_is_reproducible_and_uses_confidence(stats):
    a, b = [1, 1, 0.8, 1, 0.6], [1, 0.8, 0.8, 0.6, 0.6]
    narrow = stats.paired_bootstrap(a, b, confidence=0.8)
    wide = stats.paired_bootstrap(a, b, confidence=0.99)
    assert narrow == stats.paired_bootstrap(a, b, confidence=0.8)
    assert wide[1] <= narrow[1] <= narrow[2] <= wide[2]
    assert wide[2] - wide[1] > narrow[2] - narrow[1]


@pytest.mark.parametrize("a,b", [([], []), ([1], [0]), ([1, 0], [1]),
                                  ([float("nan"), 1], [0, 1]),
                                  ([1, 0], [float("inf"), 1]),
                                  ([[1, 0]], [[1, 0]])])
def test_paired_bootstrap_rejects_invalid_samples(stats, a, b):
    with pytest.raises(ValueError):
        stats.paired_bootstrap(a, b)


@pytest.mark.parametrize("options", [{"confidence": 0}, {"confidence": 1},
                                      {"confidence": float("nan")},
                                      {"n_resamples": 0}, {"n_resamples": 1.5}])
def test_paired_bootstrap_rejects_invalid_options(stats, options):
    with pytest.raises(ValueError):
        stats.paired_bootstrap([1, 0], [0, 1], **options)
