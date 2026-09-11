"""
Fix 6: Tests that exercise the 3-sigma scoring logic directly.

All tests use synthetic DataFrames built inline -- no real data needed.
They verify actual scoring BEHAVIOR, not just artifact structure.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from src.train import rank_week

# --- Helpers ---


def _make_telemetry(
    gateway_ids: list[str],
    start: str,
    end: str,
    freq: str = "h",
    offline_fn=None,
) -> pd.DataFrame:
    """Build a synthetic hourly telemetry DataFrame."""
    timestamps = pd.date_range(start, end, freq=freq, tz="UTC", inclusive="left")
    rows = []
    for gw in gateway_ids:
        for i, ts in enumerate(timestamps):
            rows.append(
                {
                    "gateway_id": gw,
                    "ts": ts,
                    "offline_duration_sec": offline_fn(gw, i) if offline_fn else 10.0 + (i % 5),
                    "disconnection_cnt": 1.0 + (i % 3) * 0.1,
                    "reboot_cnt": float(i % 2) * 0.1,
                }
            )
    return pd.DataFrame(rows)


def _monday(date_str: str) -> dt.date:
    return dt.date.fromisoformat(date_str)


# NOTE on rank_week window:
#   baseline window: [monday - baseline_days, monday)   (exclusive at monday)
#   recent window:   [monday - recent_days, monday)     (subset of baseline window)
#   So for monday=2026-02-09: recent = [2026-02-02, 2026-02-09)
#   Rows at exactly 2026-02-09 00:00 are OUTSIDE the window.


# --- Fix 6: Scoring behavior tests ---


def test_normal_values_no_flags():
    """
    A gateway with stable, normal telemetry (small natural variance within 3sigma)
    must produce zero flagged hours when no anomalies are injected.
    """
    gw = "GW_NORMAL"
    # 40 days of data ending at 2026-02-09 (exclusive) -- all values low variance.
    df = _make_telemetry([gw], "2025-12-31", "2026-02-09", offline_fn=lambda g, i: 10.0 + (i % 5))
    ranked, excluded = rank_week(
        df, monday=_monday("2026-02-09"), sigma=3.0, baseline_days=28, recent_days=7
    )

    assert gw not in excluded
    assert len(ranked) == 1
    assert ranked.iloc[0]["flagged_hours"] == 0


def test_value_above_3sigma_is_flagged():
    """
    A single hour with offline_duration_sec far above 3sigma of the gateway's
    own baseline must produce at least 1 flagged hour.

    Key: the spike must be at a ts INSIDE [monday-7, monday) -- NOT at monday itself.
    Key: baseline must have non-zero std so the threshold is finite.
    """
    gw = "GW_SPIKE"
    rows = []

    # Baseline: 28 days before monday=2026-02-09 = [2026-01-12, 2026-02-09)
    # Use cycling values 10..14 to get non-zero std.
    base_start = pd.Timestamp("2026-01-12 00:00", tz="UTC")
    for i in range(28 * 24):
        rows.append(
            {
                "gateway_id": gw,
                "ts": base_start + pd.Timedelta(hours=i),
                "offline_duration_sec": 10.0 + (i % 5),  # mean~12, std~1.6
                "disconnection_cnt": 1.0,
                "reboot_cnt": 0.0,
            }
        )

    # Inject spike in the RECENT window [2026-02-02, 2026-02-09):
    # Use 2026-02-02 00:00 -- safely inside the window.
    rows.append(
        {
            "gateway_id": gw,
            "ts": pd.Timestamp("2026-02-02 00:00", tz="UTC"),
            "offline_duration_sec": 99999.0,  # >> mean + 3*std
            "disconnection_cnt": 1.0,
            "reboot_cnt": 0.0,
        }
    )

    df = pd.DataFrame(rows)
    ranked, excluded = rank_week(
        df, monday=_monday("2026-02-09"), sigma=3.0, baseline_days=28, recent_days=7
    )

    assert gw not in excluded
    assert len(ranked) >= 1
    row = ranked[ranked["gateway_id"] == gw].iloc[0]
    assert row["flagged_hours"] >= 1, f"Expected >= 1 flagged hour, got {row['flagged_hours']}"
    assert row["worst_metric"] == "offline_duration_sec"


def test_exactly_at_threshold_not_flagged():
    """
    A value exactly at mean + 3*std must NOT be flagged (strict > comparison).
    """
    gw = "GW_AT_THRESHOLD"
    rows = []
    base_start = pd.Timestamp("2026-01-12 00:00", tz="UTC")
    # Baseline: values cycle 0..9 -> mean=4.5, std=2.87, threshold=4.5+3*2.87=13.1
    for i in range(28 * 24):
        rows.append(
            {
                "gateway_id": gw,
                "ts": base_start + pd.Timedelta(hours=i),
                "offline_duration_sec": float(i % 10),
                "disconnection_cnt": 1.0,
                "reboot_cnt": 0.0,
            }
        )

    baseline_vals = pd.Series([float(i % 10) for i in range(28 * 24)])
    mean_val = baseline_vals.mean()
    std_val = baseline_vals.std()
    threshold = mean_val + 3.0 * std_val

    # Recent window: one row exactly at threshold
    rows.append(
        {
            "gateway_id": gw,
            "ts": pd.Timestamp("2026-02-02 00:00", tz="UTC"),
            "offline_duration_sec": threshold,  # exactly at, NOT above
            "disconnection_cnt": 1.0,
            "reboot_cnt": 0.0,
        }
    )

    df = pd.DataFrame(rows)
    ranked, _ = rank_week(
        df, monday=_monday("2026-02-09"), sigma=3.0, baseline_days=28, recent_days=7
    )

    assert len(ranked) >= 1
    row = ranked[ranked["gateway_id"] == gw].iloc[0]
    assert (
        row["flagged_hours"] == 0
    ), f"Value exactly at threshold must NOT be flagged, got {row['flagged_hours']} flags"


def test_multiple_metric_breach_accumulates():
    """
    If both offline_duration_sec AND disconnection_cnt breach 3sigma in the
    same hour, that hour contributes 2 to flagged_hours.
    """
    gw = "GW_MULTI"
    rows = []

    # Baseline: both metrics have cycling values (non-zero std)
    base_start = pd.Timestamp("2026-01-12 00:00", tz="UTC")
    for i in range(28 * 24):
        rows.append(
            {
                "gateway_id": gw,
                "ts": base_start + pd.Timedelta(hours=i),
                "offline_duration_sec": 10.0 + (i % 5),
                "disconnection_cnt": 2.0 + (i % 3) * 0.5,
                "reboot_cnt": float(i % 2) * 0.1,
            }
        )

    # Spike BOTH metrics simultaneously in recent window
    rows.append(
        {
            "gateway_id": gw,
            "ts": pd.Timestamp("2026-02-02 00:00", tz="UTC"),
            "offline_duration_sec": 99999.0,
            "disconnection_cnt": 99999.0,
            "reboot_cnt": 0.0,
        }
    )

    df = pd.DataFrame(rows)
    ranked, _ = rank_week(
        df, monday=_monday("2026-02-09"), sigma=3.0, baseline_days=28, recent_days=7
    )
    row = ranked[ranked["gateway_id"] == gw].iloc[0]

    # 2 metrics breached in 1 hour -> flagged_hours >= 2
    assert (
        row["flagged_hours"] >= 2
    ), f"Expected >= 2 (multi-metric breach), got {row['flagged_hours']}"


def test_no_recent_telemetry_scores_zero():
    """
    A gateway with sufficient baseline but zero rows in the recent window
    must score 0 -- not crash, not raise.
    """
    gw = "GW_NO_RECENT"
    rows = []
    base_start = pd.Timestamp("2026-01-12 00:00", tz="UTC")
    # Only 28 days of baseline, NOTHING in recent [2026-02-02, 2026-02-09)
    for i in range(28 * 24):
        rows.append(
            {
                "gateway_id": gw,
                "ts": base_start + pd.Timedelta(hours=i),
                "offline_duration_sec": 10.0 + (i % 5),
                "disconnection_cnt": 1.0,
                "reboot_cnt": 0.0,
            }
        )

    df = pd.DataFrame(rows)
    ranked, excluded = rank_week(
        df, monday=_monday("2026-02-09"), sigma=3.0, baseline_days=28, recent_days=7
    )

    # No recent rows -> flagged_hours=0 or gateway absent from ranked
    if gw in ranked["gateway_id"].values:
        assert ranked[ranked["gateway_id"] == gw].iloc[0]["flagged_hours"] == 0
    assert gw not in excluded


def test_insufficient_baseline_excluded():
    """
    A gateway with fewer than MIN_BASELINE_HOURS rows in the baseline window
    must be in the excluded list and NOT in the ranked output.
    """
    gw_short = "GW_NEW"
    gw_normal = "GW_NORMAL"
    rows = []

    base_start = pd.Timestamp("2026-01-12 00:00", tz="UTC")
    # Normal gateway: 28 days of baseline + recent rows (all inside [2026-01-12, 2026-02-09))
    for i in range(28 * 24 + 7 * 24):
        rows.append(
            {
                "gateway_id": gw_normal,
                "ts": base_start + pd.Timedelta(hours=i),
                "offline_duration_sec": 10.0 + (i % 5),
                "disconnection_cnt": 1.0,
                "reboot_cnt": 0.0,
            }
        )
    # New gateway: only 5 hours inside the baseline window [2026-01-12, 2026-02-09)
    # -- do NOT add rows in the recent window, that would inflate the count.
    for i in range(5):
        rows.append(
            {
                "gateway_id": gw_short,
                "ts": base_start + pd.Timedelta(hours=i),
                "offline_duration_sec": 10.0,
                "disconnection_cnt": 1.0,
                "reboot_cnt": 0.0,
            }
        )

    df = pd.DataFrame(rows)
    ranked, excluded = rank_week(
        df, monday=_monday("2026-02-09"), sigma=3.0, baseline_days=28, recent_days=7
    )

    assert (
        gw_short in excluded
    ), f"Expected {gw_short} in excluded (5 baseline rows < MIN_BASELINE_HOURS=24)"
    assert gw_short not in ranked["gateway_id"].values, f"{gw_short} must not appear in rankings"
    assert gw_normal not in excluded
