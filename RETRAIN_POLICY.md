# Retrain Policy — LPDG Gateway Prioritization
**LPDG Innovation Hub Selection Challenge 2026 — MLOps Track**

---

## 1. Principle & Objectives

Model retraining is an operational decision that consumes computational resources and alters the ranking of field technician visits. Autonomous, unverified retraining introduces risk of catastrophic regression in live operations.

**Core Policy Invariants:**
1. Retraining is triggered by objective criteria, but promotion to `ACTIVE` is gated by validation.
2. The drift monitor informs retraining; it **never** triggers retraining automatically.
3. Every retrained model must pass the €380/€600 economic validation gate before promotion.

---

## 2. Retraining Trigger Conditions

Retraining is scheduled under either of two conditions:

### Trigger A: Consecutive Drift Flags (Event-Driven)
- **Condition:** The drift monitor (`src/drift_monitor.py`) flags schema, population, or distribution drift for **3 consecutive weeks** (`consecutive_flagged_weeks >= 3`).
- **Rationale:** Transient single-week spikes (e.g. temporary regional weather events, cellular base-station maintenance) should not invalidate the model. Three consecutive weeks indicate structural changes in gateway telemetry behavior or network topology.

### Trigger B: Ground-Truth Accumulation (Cadence-Driven)
- **Condition:** Monthly cadence, or upon receipt of **≥50 newly resolved field visit outcomes** in `field_visits.csv`.
- **Rationale:** Ground truth from technician visits (`"Fehler behoben"` vs. `"Kein Fehler gefunden"`) accumulates gradually. Retraining on new ground truth updates historical gateway reliability priors.

---

## 3. Pre-Promotion Validation Gate

Before any candidate model $v_{new}$ is promoted to `ACTIVE`, it must pass an automated comparison against the currently active model $v_{active}$ across held-out historical weeks:

### Economic Metric: Cost Impact Framework

$$\text{Net Cost} = (N_{\text{false visits}} \times €380) - (N_{\text{faults fixed}} \times €600)$$

- **Pass Condition:** $\text{Net Cost}(v_{new}) \le \text{Net Cost}(v_{active})$ on the evaluation slice.
- **Degeneracy Check:** The candidate version must generate distinct rank distributions (no uniform zero-scores or constant ranks).

---

## 4. Promotion & Rollback Protocol

1. **Training:** Candidate model trained with `python -m src.train --version <id>` (creates `models/<id>.json` without modifying `models/ACTIVE`).
2. **Evaluation:** Evaluated on validation slice against cost baseline.
3. **Promotion:** Explicit promotion via `python -m src.train --promote` or `POST /api/pipeline/train` with `promote: true`.
4. **Immediate Rollback Trigger:** If live field operations report a hit-rate regression across 2 consecutive operating weeks:
   ```bash
   python -m src.rollback to <previous_version> --reason "Regressed hit rate in operating weeks"
   python -m src.rollback verify
   ```
