from __future__ import annotations

from collections.abc import Sequence
from math import comb, isfinite
from numbers import Integral

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    if len(human) != len(judge) or len(human) == 0:
        raise ValueError("human and judge must have the same non-zero length")
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for expected, predicted in zip(human, judge):
        if expected not in ("PASS", POS) or predicted not in ("PASS", POS):
            raise ValueError("labels must be PASS or FAIL")
        key = ("tp" if expected == POS else "fp") if predicted == POS else (
            "fn" if expected == POS else "tn"
        )
        counts[key] += 1
    return counts


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    counts = confusion(human, judge)
    predicted_failures = counts["tp"] + counts["fp"]
    actual_failures = counts["tp"] + counts["fn"]
    precision = counts["tp"] / predicted_failures if predicted_failures else 0.0
    recall = counts["tp"] / actual_failures if actual_failures else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    counts = confusion(human, judge)
    n = len(human)
    observed = (counts["tp"] + counts["tn"]) / n
    human_fail = (counts["tp"] + counts["fn"]) / n
    judge_fail = (counts["tp"] + counts["fp"]) / n
    expected = human_fail * judge_fail + (1 - human_fail) * (1 - judge_fail)
    if expected == 1.0:
        raise ValueError("kappa is undefined when expected agreement is 1")
    return (observed - expected) / (1 - expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    if any(not isfinite(rate) or not 0 <= rate <= 1
           for rate in (observed_rate, sensitivity, specificity)):
        raise ValueError("rates must be finite values between 0 and 1")
    denominator = sensitivity + specificity - 1
    if denominator <= 0:
        raise ValueError("sensitivity + specificity must exceed 1")
    corrected = (observed_rate + specificity - 1) / denominator
    return min(1.0, max(0.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    import numpy as np
    from scipy.stats import bootstrap

    left, right = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if left.ndim != 1 or right.ndim != 1 or left.size != right.size or left.size < 2:
        raise ValueError("paired samples must be one-dimensional, equal length and contain at least two items")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("paired samples must contain only finite values")
    if not isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if isinstance(n_resamples, bool) or not isinstance(n_resamples, int) or n_resamples < 1:
        raise ValueError("n_resamples must be a positive integer")
    if np.array_equal(left, right):
        return 0.0, 0.0, 0.0

    def difference(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    result = bootstrap((left, right), difference, paired=True, method="percentile",
                       n_resamples=n_resamples, confidence_level=confidence,
                       rng=np.random.default_rng(rng))
    return float(difference(left, right)), float(result.confidence_interval.low), float(result.confidence_interval.high)


def _validate_pass_k(n: int, c: int, k: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in (n, c, k)):
        raise ValueError("n, c and k must be integers")
    if not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError("require 0 <= c <= n and 1 <= k <= n")


def pass_at_k(n: int, c: int, k: int) -> float:
    _validate_pass_k(n, c, k)
    return (comb(n, k) - comb(n - c, k)) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    _validate_pass_k(n, c, k)
    return comb(c, k) / comb(n, k)
