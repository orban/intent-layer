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
    """Check if two confidence intervals overlap (visual heuristic only).

    Returns True if the intervals share any range. Used for dashboard
    display, NOT as a significance test. For significance decisions, use
    McNemar's exact test (paired data) or Fisher's exact test (unpaired).
    """
    return ci_a[0] <= ci_b[1] and ci_b[0] <= ci_a[1]


def mcnemar_test(b: int, c: int) -> dict:
    """McNemar's test for paired binary outcomes using exact binomial.

    Args:
        b: pairs where condition A passes, B fails
        c: pairs where condition A fails, B passes

    Returns:
        dict with p_value, n_discordant, a_wins, b_wins
    """
    n = b + c
    if n == 0:
        return {"p_value": 1.0, "n_discordant": 0, "a_wins": b, "b_wins": c}

    k = max(b, c)
    p_value = 0.0
    for i in range(k, n + 1):
        p_value += math.comb(n, i) * 0.5**n
    p_value = min(p_value * 2, 1.0)  # two-sided

    return {"p_value": p_value, "n_discordant": n, "a_wins": b, "b_wins": c}


def fisher_exact_test(a_pass: int, a_total: int, b_pass: int, b_total: int) -> dict:
    """Fisher's exact test for 2x2 contingency table (two-sided).

    Compares pass rates between two independent groups (e.g., condition A
    vs condition B for a single task). Uses hypergeometric distribution
    to compute exact p-value without scipy.

    Args:
        a_pass, a_total: successes and total trials for group A
        b_pass, b_total: successes and total trials for group B

    Returns:
        dict with p_value, a_rate, b_rate, rate_diff
    """
    a_fail = a_total - a_pass
    b_fail = b_total - b_pass
    n = a_total + b_total
    row1 = a_pass + b_pass  # total passes
    row2 = a_fail + b_fail  # total fails

    if n == 0:
        return {"p_value": 1.0, "a_rate": 0.0, "b_rate": 0.0, "rate_diff": 0.0}

    # Probability of a specific table under H0 (hypergeometric)
    def table_prob(a_p: int) -> float:
        b_p = row1 - a_p
        a_f = a_total - a_p
        b_f = b_total - b_p
        if any(x < 0 for x in (a_p, b_p, a_f, b_f)):
            return 0.0
        return (
            math.comb(a_total, a_p)
            * math.comb(b_total, b_p)
            / math.comb(n, row1)
        )

    # Two-sided: sum probabilities of tables as extreme or more extreme
    observed_prob = table_prob(a_pass)
    p_value = 0.0
    for i in range(max(0, row1 - b_total), min(row1, a_total) + 1):
        prob = table_prob(i)
        if prob <= observed_prob + 1e-12:  # tolerance for float comparison
            p_value += prob

    a_rate = a_pass / a_total if a_total else 0.0
    b_rate = b_pass / b_total if b_total else 0.0
    return {
        "p_value": round(min(p_value, 1.0), 4),
        "a_rate": round(a_rate, 4),
        "b_rate": round(b_rate, 4),
        "rate_diff": round(b_rate - a_rate, 4),
    }
