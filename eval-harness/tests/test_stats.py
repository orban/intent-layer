# tests/test_stats.py
import pytest
from lib.stats import _inverse_normal_cdf, wilson_score_interval, ci_overlap, mcnemar_test


class TestInverseNormalCDF:
    def test_median(self):
        """Φ⁻¹(0.5) = 0 (median of standard normal)."""
        assert abs(_inverse_normal_cdf(0.5)) < 1e-6

    def test_known_quantiles(self):
        """Check against well-known z-scores."""
        # z for 95th percentile ≈ 1.6449
        assert abs(_inverse_normal_cdf(0.95) - 1.6449) < 0.001
        # z for 97.5th percentile ≈ 1.9600
        assert abs(_inverse_normal_cdf(0.975) - 1.9600) < 0.001
        # z for 5th percentile ≈ -1.6449 (symmetry)
        assert abs(_inverse_normal_cdf(0.05) + 1.6449) < 0.001

    def test_symmetry(self):
        """Φ⁻¹(p) = -Φ⁻¹(1-p) by symmetry of normal distribution."""
        for p in [0.01, 0.1, 0.25, 0.4]:
            assert abs(_inverse_normal_cdf(p) + _inverse_normal_cdf(1 - p)) < 1e-6

    def test_boundary_errors(self):
        """p must be in open interval (0, 1)."""
        with pytest.raises(ValueError):
            _inverse_normal_cdf(0)
        with pytest.raises(ValueError):
            _inverse_normal_cdf(1)
        with pytest.raises(ValueError):
            _inverse_normal_cdf(-0.1)
        with pytest.raises(ValueError):
            _inverse_normal_cdf(1.1)

    def test_tail_regions(self):
        """Values in the low/high tail regions (p < 0.02425, p > 0.97575)."""
        # Low tail
        z_low = _inverse_normal_cdf(0.01)
        assert z_low < -2.0
        assert abs(z_low - (-2.3263)) < 0.001
        # High tail
        z_high = _inverse_normal_cdf(0.99)
        assert z_high > 2.0
        assert abs(z_high - 2.3263) < 0.001


class TestWilsonScoreInterval:
    def test_zero_successes(self):
        """0/10 — lower bound near 0 but upper bound > 0."""
        lower, upper, center = wilson_score_interval(0, 10, 0.90)
        assert lower == 0.0
        assert upper > 0.0
        assert upper < 0.30  # shouldn't be too wide
        assert center > 0.0  # Wilson center is pulled away from 0

    def test_all_successes(self):
        """10/10 — upper bound near 1 but lower bound < 1."""
        lower, upper, center = wilson_score_interval(10, 10, 0.90)
        assert lower > 0.70
        assert lower < 1.0
        assert upper == 1.0
        assert center < 1.0  # Wilson center is pulled away from 1

    def test_half_successes(self):
        """5/10 — center at 0.50, roughly symmetric bounds."""
        lower, upper, center = wilson_score_interval(5, 10, 0.90)
        assert center == 0.5
        # Bounds should be roughly symmetric around 0.5
        assert abs((0.5 - lower) - (upper - 0.5)) < 0.01

    def test_zero_trials(self):
        """0 trials — degenerate case returns full [0, 1] range."""
        lower, upper, center = wilson_score_interval(0, 0, 0.90)
        assert lower == 0.0
        assert upper == 1.0
        assert center == 0.0

    def test_single_trial_pass(self):
        """1/1 — very wide CI because n=1 is barely informative."""
        lower, upper, center = wilson_score_interval(1, 1, 0.90)
        assert lower > 0.0
        assert upper == 1.0
        assert center < 1.0

    def test_single_trial_fail(self):
        """0/1 — wide CI, but upper bound should be well below 1."""
        lower, upper, center = wilson_score_interval(0, 1, 0.90)
        assert lower == 0.0
        assert upper < 1.0
        assert center > 0.0

    def test_our_eval_data(self):
        """5/8 at 90% — matches our real eval scenario.

        Expected: ~[36%, 84%] confirming paper's 2-4% differences
        are well within noise.
        """
        lower, upper, center = wilson_score_interval(5, 8, 0.90)
        assert 0.30 < lower < 0.45
        assert 0.75 < upper < 0.90
        assert 0.55 < center < 0.70

    def test_higher_confidence_widens_interval(self):
        """95% CI should be wider than 90% CI for same data."""
        l90, u90, _ = wilson_score_interval(5, 10, 0.90)
        l95, u95, _ = wilson_score_interval(5, 10, 0.95)
        assert l95 <= l90
        assert u95 >= u90

    def test_more_data_narrows_interval(self):
        """50/100 should give narrower CI than 5/10 (same proportion)."""
        l_small, u_small, _ = wilson_score_interval(5, 10, 0.90)
        l_large, u_large, _ = wilson_score_interval(50, 100, 0.90)
        width_small = u_small - l_small
        width_large = u_large - l_large
        assert width_large < width_small


class TestCIOverlap:
    def test_overlapping(self):
        """Two clearly overlapping intervals."""
        assert ci_overlap((0.3, 0.7), (0.5, 0.9)) is True

    def test_non_overlapping(self):
        """Two clearly separated intervals."""
        assert ci_overlap((0.1, 0.3), (0.5, 0.8)) is False

    def test_touching(self):
        """Intervals that share exactly one point still count as overlapping."""
        assert ci_overlap((0.1, 0.5), (0.5, 0.9)) is True

    def test_contained(self):
        """One interval fully contained within another."""
        assert ci_overlap((0.2, 0.8), (0.4, 0.6)) is True

    def test_identical(self):
        """Same interval overlaps with itself."""
        assert ci_overlap((0.3, 0.7), (0.3, 0.7)) is True


class TestMcNemarTest:
    def test_mcnemar_perfect_split(self):
        """All discordant pairs go one way — highly significant."""
        result = mcnemar_test(0, 10)
        assert result["p_value"] < 0.01
        assert result["n_discordant"] == 10
        assert result["a_wins"] == 0
        assert result["b_wins"] == 10

    def test_mcnemar_even_split(self):
        """Equal discordant pairs — not significant at all."""
        result = mcnemar_test(5, 5)
        assert result["p_value"] == 1.0
        assert result["n_discordant"] == 10
        assert result["a_wins"] == 5
        assert result["b_wins"] == 5

    def test_mcnemar_no_discordant(self):
        """No discordant pairs — p=1.0 by convention."""
        result = mcnemar_test(0, 0)
        assert result["p_value"] == 1.0
        assert result["n_discordant"] == 0

    def test_mcnemar_single_pair(self):
        """Single discordant pair — two-sided exact binomial gives p=1.0."""
        result = mcnemar_test(0, 1)
        assert result["p_value"] == 1.0
        assert result["n_discordant"] == 1
        assert result["a_wins"] == 0
        assert result["b_wins"] == 1
