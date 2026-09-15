"""Validate predictions.csv format — mimics challenge validate_submission.py logic."""

import csv
import pathlib
import sys

pred_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("predictions.csv")
if not pred_path.exists():
    print(f"ERROR: {pred_path} not found")
    sys.exit(1)

REQUIRED_COLS = {"week_start", "rank", "gateway_id", "score", "reason"}
EXPECTED_ROWS = 120
VISITS_PER_WEEK = 15

rows = list(csv.DictReader(pred_path.open(encoding="utf-8")))
cols = set(rows[0].keys()) if rows else set()

errors = []

# Column check
missing = REQUIRED_COLS - cols
if missing:
    errors.append(f"Missing columns: {missing}")

extra = cols - REQUIRED_COLS
if extra:
    print(f"  [INFO] Extra columns (OK): {extra}")

# Row count
if len(rows) != EXPECTED_ROWS:
    errors.append(f"Expected {EXPECTED_ROWS} rows, got {len(rows)}")

# Per-week checks
weeks = {}
for r in rows:
    w = r["week_start"]
    weeks.setdefault(w, []).append(r)

print(f"\n  Rows      : {len(rows)}")
print(f"  Columns   : {sorted(cols)}")
print(f"  Weeks     : {sorted(weeks.keys())}")
print(f"  Week count: {len(weeks)}")

for week, week_rows in sorted(weeks.items()):
    if len(week_rows) != VISITS_PER_WEEK:
        errors.append(f"Week {week}: expected {VISITS_PER_WEEK} rows, got {len(week_rows)}")
    ranks = [int(r["rank"]) for r in week_rows]
    if sorted(ranks) != list(range(1, VISITS_PER_WEEK + 1)):
        errors.append(f"Week {week}: ranks are not 1-15: {sorted(ranks)}")
    for r in week_rows:
        try:
            float(r["score"])
        except ValueError:
            gw = r["gateway_id"]
            sc = r["score"]
            errors.append(f"Week {week}: non-numeric score '{sc}' for gateway {gw}")
    empty_ids = [r for r in week_rows if not r["gateway_id"].strip()]
    if empty_ids:
        errors.append(f"Week {week}: {len(empty_ids)} rows with empty gateway_id")
    empty_reasons = [r for r in week_rows if not r["reason"].strip()]
    if empty_reasons:
        errors.append(f"Week {week}: {len(empty_reasons)} rows with empty reason")

if errors:
    print("\n  [FAIL] Validation errors:")
    for e in errors:
        print(f"    x {e}")
    sys.exit(1)
else:
    print("\n  [PASS] predictions.csv is valid")
    print("         120 rows, 8 weeks x 15 visits, ranks 1-15 per week")
    sys.exit(0)
