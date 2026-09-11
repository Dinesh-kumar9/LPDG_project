# Retrain Policy â€” LPDG Gateway Prioritization
**LPDG Innovation Hub Selection Challenge 2026 â€” MLOps Track**

---

## 1. Principle & Objectives

Model retraining is an operational decision that consumes computational resources and alters the ranking of field technician visits. Autonomous, unverified retraining introduces risk of catastrophic regression in live operations.

**Core Policy Invariants:**
1. Retraining is triggered by objective criteria, but promotion to `ACTIVE` is gated by validation.
2. The drift monitor informs retraining; it **never** triggers retraining automatically.
3. Every retrained model must pass the â‚¬380/â‚¬600 economic validation gate before promotion.

---

## 2. Retraining Trigger Conditions

Retraining is scheduled under either of two conditions:

### Trigger A: Consecutive Drift Flags (Event-Driven)
- **Condition:** The drift monitor (`src/drift_monitor.py`) flags schema, population, or distribution drift for **3 consecutive weeks** (`consecutive_flagged_weeks >= 3`).
- **Rationale:** Transient single-week spikes (e.g. temporary regional weather events, cellular base-station maintenance) should not invalidate the model. Three consecutive weeks indicate structural changes in gateway telemetry behavior or network topology.

### Trigger B: Ground-Truth Accumulation (Cadence-Driven)
- **Condition:** Monthly cadence, or upon receipt of **â‰¥50 newly resolved field visit outcomes** in `field_visits.csv`.
- **Rationale:** Ground truth from technician visits (`"Fehler behoben"` vs. `"Kein Fehler gefunden"`) accumulates gradually. Retraining on new ground truth updates historical gateway reliability priors.

---


## 3. Pre-Promotion Validation (Operator-Run Procedure)

Before promoting a candidate model to ACTIVE, the operator must verify it does
not regress against the currently active model. This is an **operator-run
procedure**, not an automated gate.

### Recommended Validation Steps

1. Train candidate without promoting:
   ```bash
   python -m src.train --data ./data --version <candidate_name>
   ```
2. Run predictions for both candidate and active on held-out weeks:
   ```bash
   python -m src.predict --data ./data --version <candidate_name> --out candidate.csv
   python -m src.predict --data ./data --out active.csv
   ```
3. Compare ranking overlap and score distributions across the 8 scored weeks.
4. Check for degeneracy (all scores zero, all same gateway, constant ranks).
   The `v2_broken` rollback lifecycle test demonstrates detecting a sigma=999
   model that produces meaningless rankings.
5. Promote only if candidate rankings are plausible and non-degenerate:
   ```bash
   python -m src.train --promote --version <candidate_name>
   ```
6. Run rollback verify to confirm byte-identical output:
   ```bash
   python -m src.rollback verify
   ```

### Economic Framework (Reference Only)

The €380/€600 cost framework is the theoretical basis for visit prioritization.
Automated economic validation against `field_visits.csv` outcomes is **not
implemented in this submission** -- it is listed as a realistic two-weeks-away
improvement in DECISIONS.md ADR 0006.

If `field_visits.csv` outcomes are available, the operator can manually
compute the net cost metric per candidate version before promoting:

```
Net Cost = (N_false_visits × €380) - (N_faults_fixed × €600)
Promote if: Net_Cost(candidate) <= Net_Cost(active)
```
## 4. Promotion & Rollback Protocol

1. **Training:** Candidate model trained with `python -m src.train --version <id>` (creates `models/<id>.json` without modifying `models/ACTIVE`).
2. **Evaluation:** Evaluated on validation slice against cost baseline.
3. **Promotion:** Explicit promotion via `python -m src.train --promote` or `POST /api/pipeline/train` with `promote: true`.
4. **Immediate Rollback Trigger:** If live field operations report a hit-rate regression across 2 consecutive operating weeks:
   ```bash
   python -m src.rollback to <previous_version> --reason "Regressed hit rate in operating weeks"
   python -m src.rollback verify
   ```
