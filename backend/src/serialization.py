"""
Canonical prediction serialization and hashing utilities.

These functions are the SINGLE authoritative serialization path shared by:
  - train.py  (compute_verify_hash at training time)
  - predict.py (write predictions.csv at inference time)
  - rollback.py verify() (re-compute hash after pointer swap)
  - determinism tests

Having one module here (rather than private functions in train.py) prevents
the coupling that would break predict.py if train.py is ever refactored.

Invariants that make predictions byte-identical across platforms:
  - Rows sorted: week_start ASC, score DESC, gateway_id ASC (stable tiebreak)
  - rank re-derived from sort order (not inherited from intermediate state)
  - Exactly 5 columns in fixed order: week_start, rank, gateway_id, score, reason
  - float_format="%.1f" — scores rendered with exactly 1 decimal place
  - lineterminator="\\n" — Unix newlines, overriding os.linesep on Windows
  - UTF-8 encoding throughout
"""

from __future__ import annotations

import hashlib
import pathlib

import pandas as pd


def serialize_predictions_canonical(predictions: pd.DataFrame) -> bytes:
    """
    Deterministic byte serialization of a predictions DataFrame.

    This is the single canonical path that guarantees:
        training-time hash == predict.py output hash == rollback verify hash

    Why one function:
        Previously train.py, rollback.py, and predict.py each had slightly
        different serialization (different sort orders, missing float_format,
        inconsistent column selection). Three subtly different byte streams
        meant the stored hash only matched one of them. This function closes
        all three gaps.
    """
    df = predictions.copy()
    df = df.sort_values(
        ["week_start", "score", "gateway_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    df["rank"] = df.groupby("week_start").cumcount() + 1
    df = df[["week_start", "rank", "gateway_id", "score", "reason"]]
    return str(df.to_csv(index=False, float_format="%.1f", lineterminator="\n")).encode("utf-8")


def hash_predictions_canonical(predictions: pd.DataFrame) -> str:
    """SHA-256 over the canonical byte serialization of a predictions DataFrame."""
    return "sha256:" + hashlib.sha256(serialize_predictions_canonical(predictions)).hexdigest()


def hash_predictions_file(path: pathlib.Path) -> str:
    """SHA-256 hash of a predictions CSV file on disk."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
