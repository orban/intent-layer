# lib/stats.py
"""Statistical functions for eval harness confidence intervals.

Ported from cerberus/src/stats.ts (lines 7-176). Wilson Score intervals
are better than Wald for small samples and extreme proportions (0%/100%).
The inverse normal CDF approximation (Abramowitz & Stegun 26.2.23) avoids
a scipy dependency while maintaining ~4.5e-4 accuracy.
"""
from __future__ import annotations

import math


def _inverse_normal_cdf(p: float) -> float:
    """Rational approximation of the inverse normal CDF.

    Abramowitz & Stegun formula 26.2.23. Three-region piecewise:
    lower tail (p < 0.02425), central region, upper tail (p > 0.97575).
    Accurate to ~4.5e-4 absolute error.
    """
    if p <= 0 or p >= 1:
        raise ValueError(f"p must be in (0, 1), got {p}")

    # Coefficients for central region rational approximation
    a1 = -3.969683028665376e1
    a2 = 2.209460984245205e2
    a3 = -2.759285104469687e2
    a4 = 1.383577518672690e2
    a5 = -3.066479806614716e1
    a6 = 2.506628277459239e0

    b1 = -5.447609879822406e1
    b2 = 1.615858368580409e2
    b3 = -1.556989798598866e2
    b4 = 6.680131188771972e1
    b5 = -1.328068155288572e1

    # Coefficients for tail regions
    c1 = -7.784894002430293e-3
    c2 = -3.223964580411365e-1
    c3 = -2.400758277161838e0
    c4 = -2.549732539343734e0
    c5 = 4.374664141464968e0
    c6 = 2.938163982698783e0

    d1 = 7.784695709041462e-3
    d2 = 3.224671290700398e-1
    d3 = 2.445134137142996e0
    d4 = 3.754408661907416e0

    p_low = 0.02425
    p_high = 1 - p_low

    if p < p_low:
        # Lower tail
        q = math.sqrt(-2 * math.log(p))
        return (
            (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6)
            / ((((d1 * q + d2) * q + d3) * q + d4) * q + 1)
        )
    elif p <= p_high:
        # Central region
        q = p - 0.5
        r = q * q
        return (
            ((((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) * q)
            / (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1)
        )
    else:
        # Upper tail (symmetric to lower)
        q = math.sqrt(-2 * math.log(1 - p))
        return -(
            (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6)
            / ((((d1 * q + d2) * q + d3) * q + d4) * q + 1)
        )


def wilson_score_interval(
    successes: int, n: int, confidence: float = 0.90
) -> tuple[float, float, float]:
    """Wilson Score confidence interval for a binomial proportion.

    Returns (lower, upper, center) as floats in [0, 1].
    Wilson intervals are preferred over Wald (normal approximation) because
    they don't collapse at 0% or 100% and have better coverage for small n.
    """
    if n == 0:
        return (0.0, 1.0, 0.0)

    z = _inverse_normal_cdf(1 - (1 - confidence) / 2)
    z2 = z * z
    p_hat = successes / n

    denominator = 1 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denominator
    spread = (z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))) / denominator

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return (round(lower, 4), round(upper, 4), round(center, 4))


def ci_overlap(ci_a: tuple[float, float], ci_b: tuple[float, float]) -> bool:
    """Check if two confidence intervals overlap.

    Returns True if the intervals share any range. Non-overlapping CIs
    at 90% confidence suggest a statistically meaningful difference.
    """
    return ci_a[0] <= ci_b[1] and ci_b[0] <= ci_a[1]
