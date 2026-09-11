"""
Fix 7: Regression tests for count_consecutive_flags() logic.
Tests the documented 3-consecutive-week retrain policy trigger.
"""

from __future__ import annotations

import json
import pathlib

from src.drift_monitor import count_consecutive_flags


def _write_report(reports_dir: pathlib.Path, date_str: str, flagged: bool) -> None:
    """Write a minimal drift report JSON file for a given date."""
    report = {
        "checked_at": f"{date_str}T10:00:00+00:00",
        "drift_flagged": flagged,
        "summary": "Drift detected." if flagged else "No drift detected.",
    }
    (reports_dir / f"{date_str}.json").write_text(json.dumps(report), encoding="utf-8")


def test_empty_reports_dir_returns_zero(tmp_path):
    """No report files -> consecutive count is 0."""
    assert count_consecutive_flags(tmp_path) == 0


def test_single_drift_flag_gives_count_1(tmp_path):
    """One drift report -> consecutive count = 1."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    assert count_consecutive_flags(tmp_path) == 1


def test_two_consecutive_drift_flags(tmp_path):
    """Two consecutive drift weeks -> count = 2."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    _write_report(tmp_path, "2026-01-13", flagged=True)
    assert count_consecutive_flags(tmp_path) == 2


def test_three_consecutive_flags_reaches_threshold(tmp_path):
    """Three consecutive drift weeks -> count = 3 (retrain threshold)."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    _write_report(tmp_path, "2026-01-13", flagged=True)
    _write_report(tmp_path, "2026-01-20", flagged=True)
    assert count_consecutive_flags(tmp_path) == 3


def test_clean_week_resets_consecutive_count(tmp_path):
    """A clean week after two drift weeks resets the count to 0."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    _write_report(tmp_path, "2026-01-13", flagged=True)
    _write_report(tmp_path, "2026-01-20", flagged=False)  # clean week
    assert count_consecutive_flags(tmp_path) == 0


def test_drift_after_clean_week_counts_from_latest(tmp_path):
    """[drift, clean, drift] -> count = 1, not 2. Clean week resets the streak."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    _write_report(tmp_path, "2026-01-13", flagged=False)
    _write_report(tmp_path, "2026-01-20", flagged=True)
    assert count_consecutive_flags(tmp_path) == 1


def test_non_consecutive_sequence_correct_count(tmp_path):
    """[drift, clean, drift, drift] -> count = 2 (last two are consecutive)."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    _write_report(tmp_path, "2026-01-13", flagged=False)
    _write_report(tmp_path, "2026-01-20", flagged=True)
    _write_report(tmp_path, "2026-01-27", flagged=True)
    assert count_consecutive_flags(tmp_path) == 2


def test_single_clean_report_gives_zero(tmp_path):
    """A single clean report -> count = 0."""
    _write_report(tmp_path, "2026-01-06", flagged=False)
    assert count_consecutive_flags(tmp_path) == 0


def test_corrupted_report_stops_count(tmp_path):
    """A corrupted JSON file stops the consecutive count at that point."""
    _write_report(tmp_path, "2026-01-06", flagged=True)
    _write_report(tmp_path, "2026-01-13", flagged=True)
    (tmp_path / "2026-01-20.json").write_text("{{invalid json", encoding="utf-8")
    # Sorted reverse: 2026-01-20 (corrupt, stops), 2026-01-13 (flagged), 2026-01-06 (flagged)
    # count_consecutive_flags reads most-recent first, stops at corrupt file -> count = 0
    assert count_consecutive_flags(tmp_path) == 0
