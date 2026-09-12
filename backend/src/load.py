"""
Data loading and normalization boundary for the LPDG gateway dataset.

WHY THIS FILE EXISTS AS A SINGLE BOUNDARY:
  The dataset has two confirmed data-quality issues that cause silent failures
  if handled at each call site instead of one boundary:

  1. gateway_id format mismatch:
       gateway_master.csv / field_visits.csv → colon-separated MAC ("06:5B:92:87:16:CD")
       telemetry / meter_read_success.csv   → bare uppercase hex ("065B928716CD")
     A naive join on the raw column returns zero or partial matches without raising.
     Solution: normalize to bare uppercase hex at the load boundary. Every downstream
     function assumes this format. One test (test_load.py::test_id_normalization)
     guarantees it.

  2. gateway_master.csv is Latin-1 / cp1252 encoded:
     German characters (Außenmast, Baden-Württemberg, Schaltschrank) corrupt silently
     under a default UTF-8 read. Solution: explicit encoding="latin-1" on every read.

  Both issues are handled HERE and ONLY HERE. No normalization logic anywhere else.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pandas as pd

# ─── Constants ────────────────────────────────────────────────────────────────

_BARE_HEX_RE: Final = re.compile(r"^[0-9A-Fa-f]{12}$")
_COLON_MAC_RE: Final = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Outcome strings in field_visits.csv are German. These are the exact byte
# sequences in the CSV — do not translate, do not normalise to lowercase.
OUTCOME_FAULT_FIXED: Final = "Fehler behoben"  # real fault found and repaired
OUTCOME_NO_FAULT: Final = "Kein Fehler gefunden"  # visit found nothing
OUTCOME_NO_ACCESS: Final = "Kein Zugang"  # technician could not enter site

# The only outcome that counts as a "real fault" for label extraction (Phase 3).
OUTCOME_IS_FAULT: Final[frozenset[str]] = frozenset({OUTCOME_FAULT_FIXED})

# Columns we require to be present in each source. We do not require ALL 57
# telemetry columns — only those we actually use for scoring and features.
# Schema assertions will catch any column drops in future data batches.
TELEMETRY_REQUIRED_COLS: Final[frozenset[str]] = frozenset(
    {
        "gateway_id",
        "ts_utc",
        # 3-sigma baseline metrics (Phase 1)
        "offline_duration_sec",
        "disconnection_cnt",
        "reboot_cnt",
        # Signal quality (Phase 3 features)
        "rssi_good",
        "rssi_normal",
        "rssi_bad",
        "rscp_rsrp_good",
        "rscp_rsrp_normal",
        "rscp_rsrp_bad",
        # Network type (Phase 3)
        "network_2g",
        "network_3g",
        "network_4g",
        # LoRa packet quality (Phase 3)
        "rx_nr_pkts",
        "rx_crc_bad",
        # LPDG importance scores (Phase 3)
        "reboot_importance",
        "no_conn_importance",
        # System health (Phase 3)
        "avg_load1",
        "avg_memfree",
    }
)

GATEWAY_MASTER_REQUIRED_COLS: Final[frozenset[str]] = frozenset(
    {
        "gateway_id",
        "tenant",
        "site_type",
        "region",
        "hw_model",
        "antenna_type",
        "fw_version",
        "installed_on",
        "n_meters_installed",
    }
)

FIELD_VISITS_REQUIRED_COLS: Final[frozenset[str]] = frozenset(
    {
        "visit_id",
        "gateway_id",
        "requested_on",
        "visited_on",
        "outcome",
    }
)

METER_READ_REQUIRED_COLS: Final[frozenset[str]] = frozenset(
    {
        "week_start",
        "gateway_id",
        "meters_expected",
        "meters_read",
    }
)

# How many master gateways are allowed to have no telemetry before we raise.
# We confirmed 52 decommissioned/new gateways as of Aug 2025. Allow up to 80
# to avoid false alarms on future batches with slightly different coverage.
_MAX_MASTER_IDS_ABSENT_FROM_TELEMETRY: Final = 80


# ─── Core normalization ────────────────────────────────────────────────────────


def normalize_gateway_id(raw: str) -> str:
    """
    Normalize a gateway identifier to bare uppercase hex (12 chars, no colons).

    Accepts both formats present in the dataset:
      - Colon-separated MAC: "06:5B:92:87:16:CD"  → "065B928716CD"
      - Bare hex (any case): "0639ea5602c1"        → "0639EA5602C1"

    Raises ValueError for anything else so callers fail fast instead of
    silently producing wrong join results.
    """
    text = str(raw).strip()
    if _COLON_MAC_RE.match(text):
        return text.replace(":", "").upper()
    upper = text.upper()
    if _BARE_HEX_RE.match(upper):
        return upper
    raise ValueError(
        f"Unrecognized gateway_id format: {raw!r}. "
        "Expected 12-char hex or colon-separated MAC address."
    )


# ─── Schema assertions ─────────────────────────────────────────────────────────


def _assert_schema(df: pd.DataFrame, required: frozenset[str], source: str) -> None:
    """
    Raise ValueError if any required column is missing.

    WHY: A missing column produces silent NaN-filled frames downstream, which
    cause wrong (and undetectable) rankings. We prefer a loud early failure.
    """
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{source}: missing required column(s): {sorted(missing)}. "
            f"Got: {sorted(df.columns.tolist())}"
        )


# ─── Individual loaders ────────────────────────────────────────────────────────


def load_telemetry(data_dir: pathlib.Path, *, validate_schema: bool = True) -> pd.DataFrame:
    """
    Load all telemetry parquet partitions from data_dir/telemetry/.

    Reads the full partition tree (month=YYYY-MM/part-0.parquet). The parquet
    files already use bare hex gateway_ids, but we normalize anyway to ensure
    case consistency and validate format.

    Returns a DataFrame with:
      - gateway_id: normalized bare hex (uppercase, 12 chars)
      - ts: UTC-aware datetime (replaces ts_utc)
      - all 57 original columns except ts_utc
    """
    tel_path = data_dir / "telemetry"
    if not tel_path.exists():
        raise FileNotFoundError(f"Telemetry directory not found: {tel_path}")

    df = pd.read_parquet(tel_path)
    if validate_schema:
        _assert_schema(df, TELEMETRY_REQUIRED_COLS, "telemetry")

    # The drift monitor deliberately loads with validate_schema=False so that it
    # can report a changed schema instead of failing before it has a report.
    # Prediction and training keep the strict default and therefore still fail
    # fast on malformed data.
    if "gateway_id" in df.columns:
        # Normalize IDs (telemetry is already bare hex but may have case differences)
        df["gateway_id"] = df["gateway_id"].apply(normalize_gateway_id)

    if "ts_utc" in df.columns:
        # Parse timestamp — use datetime.timedelta in arithmetic (not pd.Timedelta)
        # to avoid NumPy 2.x deprecation warnings on Python 3.12.
        df["ts"] = pd.to_datetime(df["ts_utc"], utc=True)
        df = df.drop(columns=["ts_utc"])

    df = df.drop_duplicates().reset_index(drop=True)

    return df


def load_gateway_master(data_dir: pathlib.Path) -> pd.DataFrame:
    """
    Load the gateway asset register.

    WHY encoding="latin-1":
      The file contains German characters (Außenmast, Baden-Württemberg,
      Schaltschrank) that are encoded in Latin-1 / cp1252. Reading with the
      default UTF-8 produces silent garbling (replacement characters) rather
      than raising an exception, making the bug invisible in test output.
      The explicit encoding= parameter is the single fix.
    """
    path = data_dir / "gateway_master.csv"
    if not path.exists():
        raise FileNotFoundError(f"gateway_master.csv not found: {path}")

    df = pd.read_csv(path, encoding="latin-1")
    _assert_schema(df, GATEWAY_MASTER_REQUIRED_COLS, "gateway_master")

    df["gateway_id"] = df["gateway_id"].apply(normalize_gateway_id)
    df["installed_on"] = pd.to_datetime(df["installed_on"], errors="coerce")
    df["decommissioned_on"] = pd.to_datetime(
        df.get("decommissioned_on", pd.Series(dtype="object")), errors="coerce"
    )

    return df


def load_field_visits(data_dir: pathlib.Path) -> pd.DataFrame:
    """
    Load historical field visit work orders.

    Outcome strings are German and kept as-is (see module-level constants).
    Use OUTCOME_IS_FAULT to derive binary fault labels — do not hardcode the
    German strings anywhere outside this module.
    """
    path = data_dir / "field_visits.csv"
    if not path.exists():
        raise FileNotFoundError(f"field_visits.csv not found: {path}")

    df = pd.read_csv(path)
    _assert_schema(df, FIELD_VISITS_REQUIRED_COLS, "field_visits")

    df["gateway_id"] = df["gateway_id"].apply(normalize_gateway_id)
    df["requested_on"] = pd.to_datetime(df["requested_on"])
    df["visited_on"] = pd.to_datetime(df["visited_on"])

    # Derived binary label — True = real fault found and fixed.
    # This is the ground truth signal for Phase 3 training.
    df["is_fault"] = df["outcome"].isin(OUTCOME_IS_FAULT)

    return df


def load_meter_read_success(data_dir: pathlib.Path) -> pd.DataFrame:
    """
    Load weekly meter read success rates.

    Note: this file ends 2026-01-26 — before the 8 scored weeks (Feb–Mar 2026).
    It is useful as a historical feature (read success rate trend) but cannot
    provide ground truth for the scored period.
    """
    path = data_dir / "meter_read_success.csv"
    if not path.exists():
        raise FileNotFoundError(f"meter_read_success.csv not found: {path}")

    df = pd.read_csv(path)
    _assert_schema(df, METER_READ_REQUIRED_COLS, "meter_read_success")

    df["gateway_id"] = df["gateway_id"].apply(normalize_gateway_id)
    df["week_start"] = pd.to_datetime(df["week_start"])

    # Derived read success rate — clipped to [0, 1] in case of data errors.
    df["read_success_rate"] = (df["meters_read"] / df["meters_expected"]).clip(0, 1)

    return df


def load_engineer_review(data_dir: pathlib.Path) -> pd.DataFrame:
    """
    Load the one-off engineer review for February 2026.

    This is a weak label source: one engineer, one day, 120 gateways.
    Kategorie values: "Schlecht" (bad) or "Normal".
    Use only as a validation signal for Phase 3 — NOT as training labels.
    """
    path = data_dir / "engineer_review_2026-02.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"engineer_review_2026-02.xlsx not found: {path}")

    df = pd.read_excel(path)

    df["gateway_id"] = df["gateway_id"].apply(normalize_gateway_id)
    df["is_bad"] = df["Kategorie"] == "Schlecht"

    return df


# ─── Combined loader ──────────────────────────────────────────────────────────


def load_all(data_dir: pathlib.Path) -> dict[str, pd.DataFrame]:
    """
    Load all five data sources and validate cross-source ID consistency.

    Returns a dict with keys:
      "telemetry", "master", "visits", "meter", "engineer_review"

    Raises ValueError if the gateway ID overlap between master and telemetry
    is unexpectedly low — which would indicate a normalization failure.

    WHY the overlap check matters:
      A naive join on un-normalized IDs returns zero rows without raising.
      The overlap check makes this failure visible immediately at load time.
    """
    sources: dict[str, pd.DataFrame] = {
        "telemetry": load_telemetry(data_dir),
        "master": load_gateway_master(data_dir),
        "visits": load_field_visits(data_dir),
        "meter": load_meter_read_success(data_dir),
        "engineer_review": load_engineer_review(data_dir),
    }

    tel_ids = set(sources["telemetry"]["gateway_id"].unique())
    master_ids = set(sources["master"]["gateway_id"].unique())

    only_in_master = master_ids - tel_ids
    if len(only_in_master) > _MAX_MASTER_IDS_ABSENT_FROM_TELEMETRY:
        raise ValueError(
            f"ID overlap check failed: {len(only_in_master)} gateway IDs appear in "
            f"gateway_master.csv but not in telemetry. Expected at most "
            f"{_MAX_MASTER_IDS_ABSENT_FROM_TELEMETRY} (decommissioned gateways). "
            "This likely means the gateway_id normalization is broken."
        )

    return sources
