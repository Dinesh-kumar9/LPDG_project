# PRD — Gateway Visit Prioritization (MLOps Track)
LPDG Innovation Hub Selection Challenge 2026

---

## 1. Problem Statement

LPDG operates a radio network of ~320 gateways relaying meter readings for a utility
customer. Gateways fail silently — nobody notices until a wrong bill or a customer
complaint surfaces weeks later. Operations can send engineers to **15 sites a week**, a
hard cap. Today that list is chosen from a spreadsheet and gut feel.

**Cost structure:**
| Event | Cost |
|---|---|
| Visit finds a real fault | €600/week saved (until fixed) |
| Visit finds nothing | €380 wasted, once |
| Broken gateway left alone | €600, repeating every week it stays broken |

The task: given data up to a Monday, output the 15 gateways worth visiting that week,
ranked, with a reason — for 8 consecutive weeks (2 Feb – 23 Mar 2026).

## 2. Scope

**Part 1 (mandatory, pass/fail):** A pipeline that runs with one command, reads from
`./data`, and writes a valid `predictions.csv` — 120 rows, 5 columns, passing
`validate_submission.py`.

**Part 2 (chosen track: MLOps, 60% of score):** Everything *around* the ranking logic,
not the ranking logic itself:
- Training and predicting as genuinely separate steps
- A versioned, file-based model registry
- Deterministic predictions (same input + version → same output)
- A drift monitor watching incoming data for shape changes
- A written, defensible retrain policy
- A rollback mechanism, tested for real, not just implemented

**Explicitly out of scope:** Building a model that beats the baseline on accuracy. The
brief states this is not required outside the ML track, and reusing `baseline_3sigma.py`'s
logic as the scoring function is an accepted, deliberate choice (see DECISIONS.md #1).

## 3. Success Metrics

| Layer | Measured by |
|---|---|
| Part 1 gate | `validate_submission.py` exits 0 |
| MLOps depth (60%) | Presence + correctness of registry, drift monitor, retrain policy, rollback — demonstrated live |
| Judgement (25%) | Ambiguities identified and defended in `DECISIONS.md` and Round 1/2 questions |
| Explaining it (15%) | Clarity of `DECISIONS.md`, the recording, and whether an operations manager would follow it |
| Internal sanity check | Own held-out validation slice, scored with the €380/€600 framework, vs. `baseline_3sigma.py` |

## 4. Data Sources & Known Issues

| File | Grain | Rows | Notes |
|---|---|---|---|
| `telemetry/month=YYYY-MM/*.parquet` | gateway × hour | 1.43M | 57 cols, Aug 2025–Mar 2026 |
| `gateway_master.csv` | gateway | 332 | **Latin-1 encoded**, not UTF-8 |
| `field_visits.csv` | work order | 642 | Historical hit-rate ≈ 35% (223/642 fixed) |
| `meter_read_success.csv` | gateway × week | 7,226 | Ends 2026-01-26, before scored window |
| `engineer_review_2026-02.xlsx` | gateway | 120 | One-off manual review, useful as a weak label sanity check |

**Two confirmed data-quality issues, both handled at the load boundary, not per-call site:**
1. `gateway_id` format differs across files — colon-separated MAC (`06:5B:92:87:16:CD`) in
   `gateway_master.csv`/`field_visits.csv` vs. bare hex (`0AF1F0E3B640`) in
   `meter_read_success.csv`/telemetry. Confirmed 100% overlap once normalized
   (strip colons, uppercase). A naive join silently returns partial/zero matches instead
   of erroring.
2. `gateway_master.csv` is Latin-1/cp1252 encoded — German characters (`Außenmast`,
   `Baden-Württemberg`) silently corrupt under a default UTF-8 read rather than raising.

## 5. Architecture

```
Raw data (parquet + CSV + xlsx)
        |
        v
Load & Normalize  ──────────────►  Drift Monitor
  - gateway_id -> bare hex,          - watches the same normalized
    uppercase, at the boundary         data for schema/shape changes
  - explicit Latin-1 decode            (new/missing columns, new
    for gateway_master.csv              gateway_ids, out-of-range
  - schema assertions                   values)
        |                                     |
        v                                     v
     Train (train.py)              triggers retrain, per
        |                          RETRAIN_POLICY.md
        v
  Model Registry (models/)  ◄────────── Rollback (rollback.py)
    - vN_<date>.json                     - flips models/ACTIVE
    - ACTIVE pointer (plain text)        - refuses unknown versions
    - rollback_log.jsonl (audit)         - logs {from, to, reason}
        |
        v
   Predict (predict.py --version vN, defaults to ACTIVE)
        |
        v
   predictions.csv  ──────► validate_submission.py
```

### Repo layout

```
├── data/                       # mounted at runtime, never committed
├── src/
│   ├── load.py                  # normalization + schema checks
│   ├── train.py                 # writes models/vN_<date>.json
│   ├── predict.py               # --version flag, default = ACTIVE
│   ├── drift_monitor.py         # run before predict
│   └── rollback.py              # list / current / to / verify
├── models/
│   ├── v1_2026-02-01.json
│   ├── ACTIVE
│   └── rollback_log.jsonl
├── tests/
│   ├── test_normalization.py
│   ├── test_determinism.py
│   └── test_rollback.py
├── RETRAIN_POLICY.md
├── DECISIONS.md
├── AI-USAGE.md
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## 6. Component Design

### 6.1 `load.py`
- Reads all five data files.
- Normalizes `gateway_id` to bare uppercase hex immediately on load — every downstream
  function assumes this format; a single test (`test_normalization.py`) guarantees it.
- Reads `gateway_master.csv` with `encoding="latin-1"` explicitly.
- Asserts expected columns are present on every file; raises with a clear message
  (not a silent `NaN`-filled frame) if the schema doesn't match.

### 6.2 `train.py`
- Input: normalized historical data up to a given cutoff date.
- Computes the ranking logic (baseline 3-sigma method, reused deliberately — see
  DECISIONS.md #1).
- Writes `models/v<N>_<date>.json` containing: version id, training window, parameters,
  a content hash of the training data, and a hash of a fixed-slice prediction (used by
  `rollback.py verify`).
- Sets the new version as `ACTIVE` only when run with `--promote` — training and
  promotion are separate actions, so a bad training run never silently goes live.

### 6.3 Model Registry
- Plain files, no database — inspectable with `cat`, safe to demo live.
- `ACTIVE` is a single-line pointer file; `rollback.py` only ever rewrites this one file.
- `rollback_log.jsonl` is append-only: `{timestamp, from_version, to_version, reason}`.

### 6.4 `predict.py`
- Loads the version named in `--version`, or `ACTIVE` if omitted.
- No randomness without a fixed seed — same version + same input data must produce
  byte-identical `predictions.csv` (`test_determinism.py` enforces this).
- Writes the 5-column, 120-row format `validate_submission.py` expects.

### 6.5 `drift_monitor.py`
- Runs against each new batch of incoming data before predict.
- Checks: column set unchanged, `gateway_id`s not wildly different from the known set,
  value ranges within historically observed bounds per column.
- Logs a clear flag (not a crash) when triggered; does **not** retrain automatically —
  it feeds a decision, it doesn't make one.

### 6.6 `RETRAIN_POLICY.md` (summary)
- Retrain when: drift flagged for 3+ consecutive weeks, OR monthly on a fixed cadence
  once new `field_visits.csv` ground truth has accumulated — whichever comes first.
- Validate before promoting: compare the candidate version's cost (€380/€600 framework)
  against `ACTIVE` on a held-out historical week; only promote if it doesn't regress.

### 6.7 `rollback.py`
```
python -m src.rollback list
python -m src.rollback current
python -m src.rollback to v1_2026-02-01 --reason "v2 regressed on validation slice"
python -m src.rollback verify
```
- `to` refuses silently-missing versions with a clear error.
- `verify` re-runs predict on a fixed slice and compares its hash against the one stored
  in that version's own JSON file — proof the swap actually took effect.
- **Tested for real**, not just implemented: train a deliberately broken version, confirm
  it's worse, roll back, confirm byte-identical recovery — committed as one real commit
  (see DECISIONS.md #2 and the Testing Plan below).

## 7. CLI / Docker Interface

```
docker compose up                          # load -> train (if no ACTIVE) -> predict -> validate
python -m src.train --promote
python -m src.predict [--version vN]
python -m src.drift_monitor
python -m src.rollback {list|current|to|verify}
```
- All settings via environment variables / flags — no hardcoded local paths.
- `./data` mounted read-only into the container, per the brief's requirement.

## 8. Testing Plan

| Test | What it proves |
|---|---|
| `test_normalization.py` | All four ID formats collapse to one; Latin-1 file decodes correctly |
| `test_determinism.py` | Same version + same input → identical output, twice |
| `test_rollback.py` | Deliberate bad version → rollback → byte-identical recovery to prior good output |
| `validate_submission.py` | Format contract — run before every hand-in |
| Manual: drift monitor | Feed it a batch with a renamed column; confirm it flags, doesn't crash |

The rollback test is the one that matters most for the live session — it's rehearsed
exactly as it will be demonstrated: break a version, prove it's worse, roll back, prove
recovery, all in under a minute.

## 9. Live Session Readiness

Per the brief, MLOps candidates get asked to roll back to a previous version live and
show it worked. Design implications already built in:
- Rollback is a pointer flip + re-predict — seconds, not minutes, fits the ~35-minute
  session budget.
- `rollback.py verify` gives an immediate, objective "it worked" signal without needing
  external ground truth (see Round 1 question on rollback interpretation).
- Training is never triggered implicitly by predict or rollback — nothing in the live
  room accidentally kicks off a long-running job.

## 10. Timeline

| Date | Milestone |
|---|---|
| Aug 30–31 | Data verified, gotchas identified, Round 1 questions submitted |
| Week 2 (Sep 1–6) | `load.py`, `train.py`, `predict.py` working end-to-end; Week 2 check-in pushed |
| Sep 7 | Round 2 questions, if any remain |
| Week 3 (Sep 7–13) | Drift monitor, retrain policy, rollback built + tested for real |
| Sep 14–16 | Docker, docs, `DECISIONS.md` finalized, screen recording, repo made public |
| Sep 16, 23:59 IST | Hand-in |

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Silent join failures from ID mismatch | Normalize once at load boundary; test enforces it |
| Live-session data has an unexpected schema | Asked in Round 1; drift monitor designed to flag, not crash, regardless of answer |
| Rollback "worked" means something we didn't build for | Asked directly in Round 1; hedge kept (internal held-out cost comparison) either way |
| Retraining accidentally runs during the live demo | Train and predict are separate CLI commands; nothing auto-triggers training |
| Repo history looks like one big commit at the end | Commit as each component lands, including the rollback test itself |

## 12. Deliverables Checklist

- [ ] `predictions.csv` — 120 rows, passes `validate_submission.py`
- [ ] `DECISIONS.md` — 5 entries, one naming the MLOps track choice
- [ ] "What it cannot do" section
- [ ] `AI-USAGE.md`
- [ ] Normal commit history (not one final commit)
- [ ] 6–8 min screen recording
- [ ] Model registry with 2+ versions
- [ ] Drift monitor, demonstrated against a shape change
- [ ] `RETRAIN_POLICY.md`
- [ ] Rollback, tested and committed as a real event
- [ ] Repo public by 23:59 IST, 16 Sep 2026 — no data in it
