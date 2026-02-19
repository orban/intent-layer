# tests/test_budget.py
import json
import subprocess
from unittest.mock import patch, MagicMock

from lib.budget import get_budget_status, check_budget, refresh_budget_snapshot, fmt_tokens


SAMPLE_NIGHTSHIFT_OUTPUT = {
    "budget_projection": {
        "remaining_tokens": 383_560,
        "will_exhaust_before_reset": True,
        "est_hours_remaining": 14.7,
        "reset_at": "Mon 24 Feb",
        "current_used_pct": 57,
        "weekly_budget": 900_000,
    }
}


class TestFmtTokens:
    def test_millions(self):
        assert fmt_tokens(1_200_000) == "1.2M"

    def test_thousands(self):
        assert fmt_tokens(384_000) == "384k"

    def test_small(self):
        assert fmt_tokens(500) == "0k"

    def test_exactly_one_million(self):
        assert fmt_tokens(1_000_000) == "1.0M"


class TestGetBudgetStatus:
    @patch("lib.budget.subprocess.run")
    def test_returns_projection_on_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(SAMPLE_NIGHTSHIFT_OUTPUT),
        )
        result = get_budget_status()
        assert result is not None
        assert result["remaining_tokens"] == 383_560
        assert result["will_exhaust_before_reset"] is True

    @patch("lib.budget.subprocess.run")
    def test_returns_none_when_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert get_budget_status() is None

    @patch("lib.budget.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="nightshift", timeout=10)
        assert get_budget_status() is None

    @patch("lib.budget.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert get_budget_status() is None

    @patch("lib.budget.subprocess.run")
    def test_returns_none_on_invalid_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        assert get_budget_status() is None

    @patch("lib.budget.subprocess.run")
    def test_returns_none_when_no_projection_key(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"some_other_key": 42}),
        )
        assert get_budget_status() is None


class TestCheckBudget:
    @patch("lib.budget.get_budget_status")
    def test_returns_none_when_nightshift_unavailable(self, mock_status):
        mock_status.return_value = None
        assert check_budget(10) is None

    @patch("lib.budget.get_budget_status")
    def test_returns_none_when_budget_sufficient(self, mock_status):
        mock_status.return_value = {
            "remaining_tokens": 10_000_000,
            "will_exhaust_before_reset": False,
            "current_used_pct": 10,
            "reset_at": "Mon 24 Feb",
        }
        # 10 tasks * 50k = 500k << 10M remaining
        assert check_budget(10) is None

    @patch("lib.budget.get_budget_status")
    def test_returns_warning_when_over_budget(self, mock_status):
        mock_status.return_value = {
            "remaining_tokens": 100_000,
            "will_exhaust_before_reset": True,
            "est_hours_remaining": 5.2,
            "current_used_pct": 89,
            "reset_at": "Mon 24 Feb",
        }
        # 240 tasks * 50k = 12M >> 100k remaining
        warning = check_budget(240)
        assert warning is not None
        assert "240 tasks" in warning
        assert "exceed remaining budget" in warning

    @patch("lib.budget.get_budget_status")
    def test_warns_on_will_exhaust_even_if_estimate_fits(self, mock_status):
        mock_status.return_value = {
            "remaining_tokens": 5_000_000,
            "will_exhaust_before_reset": True,
            "est_hours_remaining": 2.0,
            "current_used_pct": 45,
            "reset_at": "Mon 24 Feb",
        }
        # 2 tasks * 50k = 100k << 5M, but nightshift says will exhaust
        warning = check_budget(2)
        assert warning is not None
        assert "exhaust before reset" in warning

    @patch("lib.budget.get_budget_status")
    def test_returns_none_when_remaining_tokens_missing(self, mock_status):
        mock_status.return_value = {"current_used_pct": 50}
        assert check_budget(10) is None

    def test_accepts_prefetched_status(self):
        """check_budget(status=...) skips get_budget_status() call."""
        status = {
            "remaining_tokens": 100,
            "will_exhaust_before_reset": True,
            "current_used_pct": 99,
            "reset_at": "Mon 24 Feb",
        }
        warning = check_budget(10, status=status)
        assert warning is not None
        assert "exceed remaining budget" in warning

    def test_returns_none_when_remaining_is_string(self):
        """isinstance guard rejects non-numeric remaining_tokens."""
        status = {
            "remaining_tokens": "unknown",
            "will_exhaust_before_reset": False,
            "current_used_pct": 0,
            "reset_at": "Mon 24 Feb",
        }
        assert check_budget(10, status=status) is None


class TestRefreshBudgetSnapshot:
    @patch("lib.budget.subprocess.Popen")
    def test_fires_subprocess(self, mock_popen):
        refresh_budget_snapshot()
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "nightshift" in args
        assert "snapshot" in args

    @patch("lib.budget.subprocess.Popen")
    def test_ignores_file_not_found(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError
        # Should not raise
        refresh_budget_snapshot()
