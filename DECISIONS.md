# Architectural Decisions Log (ADR)
**LPDG Gateway Visit Prioritization (MLOps Track)**

---

## ADR 0008: Submission Track — MLOps (Chosen)

### Context
The LPDG Innovation Hub Selection Challenge 2026 offers two submission tracks:
- **ML Track** — optimise the gateway-ranking model for accuracy against held-out ground truth.
- **MLOps Track** — build the operational infrastructure *around* the ranking logic: model versioning, deterministic prediction, drift monitoring, a defensible retrain policy, and a rollback mechanism tested for real.

### Decision
We selected the **MLOps track**. The ranking logic deliberately reuses `baseline_3sigma.py`'s 3-sigma method as-is — not because a better model could not be built, but because the 60% of the score allocated to MLOps infrastructure represents a better return on engineering investment, and because the brief explicitly states that accuracy improvement is not required outside the ML track.

### Alternative Considered
**ML Track** — train an XGBoost / gradient-boosted model to beat the baseline on total cost.

### Why Rejected
The ML track awards marks for a model that beats the baseline on total cost, not on accuracy. Given the 18-day timeline and the operational context (weekly batch, 320 gateways, no GPU), the engineering time required to produce a reliable forward-validated cost improvement exceeds what is available. More importantly, the 3-sigma baseline already captures the signal the task cares about — silent gateway degradation. A 5–10% cost improvement over the baseline carries less evaluative signal than a fully auditable, deterministic, rollback-tested MLOps pipeline. The 60% MLOps grade rewards infrastructure that survives a live 35-minute session; the ML grade rewards a single cost number.

### What this decision de-scoped
- XGBoost / gradient-boosted uplift model (Phase 3, not implemented for this submission)
- SHAP-based feature importance in the live API (libraries kept as optional extras only)
- Ground-truth recall optimisation beyond the 3-sigma threshold

### Consequences
- **Positive:** Every MLOps component is real, auditable, and demonstrable in under 60 seconds:
  file-based model registry, versioned JSON artifacts, cryptographic hash verification, rollback tested as a genuine committed event, drift monitor with advisory flagging, a written retrain policy.
- **Positive:** The system is deterministic — same version + same input → byte-identical `predictions.csv`. This is more operationally trustworthy than a stochastic model with higher accuracy.
- **Negative:** The ranking model itself is the baseline — it will not beat a well-tuned XGBoost on the ML-track leaderboard. This is accepted and documented.

---

## ADR 0001: Separation of Training, Registry, and Prediction

### Context
In naive ML prototypes, prediction scripts frequently retrain models on the fly or execute ranking logic inline. This creates non-deterministic side-effects, prevents version audits, and makes rollback impossible during live operations.

### Decision
Decouple the pipeline into distinct, independent phases:
1. `src/load.py` establishes single boundary normalization.
2. `src/train.py` computes parameters and exports content-hashed artifacts into `models/`.
3. `models/ACTIVE` points to the authorized version.
4. `src/predict.py` reads exclusively from the declared version artifact and produces identical predictions deterministically.

### Alternative Considered
**Inline retraining on predict call** — train and rank in a single `predict.py` execution, as is common in notebook-style pipelines.

### Why Rejected
Inline retraining makes rollback impossible: there is no versioned artifact to return to, and no way to reproduce a past ranking without re-running training with the exact same data snapshot. It also violates the brief's explicit requirement for the live session: *"anything that retrains while it is trying to answer will not finish in the room"* (FAQ R2 §7.2). A separate training step, with an explicit `--promote` flag, ensures a bad training run never silently becomes the active production version.

### Consequences
- **Positive:** Full auditability, instant rollback via pointer swap, zero implicit compute during inference.
- **Negative:** Requires explicit promotion step (`--promote`).

---

## ADR 0002: File-Based Model Registry over External DB

### Context
The evaluation occurs in both automated grading and a live ~35-minute demonstration session. Dependency on external services (PostgreSQL, MLflow, AWS S3) introduces external failure modes, latency, and credential overhead.

### Decision
Implement a zero-infra, file-based model registry using `models/*.json`, a plain-text `models/ACTIVE` pointer file, and an append-only `models/rollback_log.jsonl` audit log.

### Alternative Considered
**MLflow Tracking Server** — a widely-used hosted experiment tracker with a UI, version comparison, and model staging built in.

### Why Rejected
MLflow requires a running PostgreSQL backend or SQLite file, a tracking server process, and network access at run time. All three conflict with the offline evaluation constraint (FAQ R1 §2.1: *"runs offline — assume the reviewer's machine has no internet"*). A reviewer who cannot reach the tracking server during `docker compose up` gets a failed pipeline, not a UI. A flat-file registry is inspectable with `cat models/ACTIVE` and `cat models/rollback_log.jsonl` — no service, no account, no latency.

### Consequences
- **Positive:** Inspectable with standard Unix tools (`cat`, `ls`), zero latency, 100% demo stability, safe inside containerized air-gapped environments.
- **Negative:** Limited concurrent write throughput (irrelevant for weekly batch cadence).

---

## ADR 0003: Single Normalization Boundary for Inconsistent Gateway Identifiers

### Context
Gateway IDs are represented as colon-separated MAC addresses (`06:5B:92:87:16:CD`) in asset/work-order registers, but bare hex strings (`065B928716CD`) in parquet telemetry. A naive join silently matches 0 rows without raising errors.

### Decision
Enforce bare uppercase hex normalization immediately upon data ingress in `src/load.py`. No downstream component handles colon formatting. `load_all()` asserts minimum cross-table ID overlap.

### Alternative Considered
**Per-caller normalization** — normalize gateway IDs at each join site (train.py, drift_monitor.py, API routers) rather than at a single boundary.

### Why Rejected
Any single missed call site produces a silent zero-row join result — no exception, no log, just a ranking with no gateway data. We found one such case during development (drift_monitor initially called with raw CSV IDs, producing an empty population check). Centralizing normalization at `load.py` means the fix is in one place, one test (`test_load.py::test_id_normalization`) covers all consumers, and a new data source cannot introduce the bug without touching the boundary.

### Consequences
- **Positive:** Eliminates silent join failure bug classes across all consumers.
- **Negative:** Ingress validation overhead (amortized during load).

---

## ADR 0004: Explicit Latin-1 Ingress Decoding for German Asset Metadata

### Context
`gateway_master.csv` contains German geographic and infrastructure terms (e.g. `Außenmast`, `Baden-Württemberg`, `Schaltschrank`). Default UTF-8 reading corrupts strings into replacement characters silently.

### Decision
Specify `encoding="latin-1"` explicitly on `pd.read_csv` in `load_gateway_master()`.

### Alternative Considered
**`errors='replace'` with UTF-8** — read the file as UTF-8 and replace undecodable bytes with the Unicode replacement character (`U+FFFD`).

### Why Rejected
Silent replacement produces garbled strings that pass string-type checks and enter downstream joins. A gateway with `site_type = "Au\ufffdenmast"` instead of `"Außenmast"` will fail a string equality check silently — the same failure mode as the ID normalization bug (ADR 0003). An explicit `encoding="latin-1"` reads the file correctly and is the right fix. If the file were ever re-encoded to UTF-8, the explicit parameter would still work because all Latin-1 characters are valid UTF-8 codepoints. Failure mode is loud (`UnicodeDecodeError`) rather than silent.

### Consequences
- **Positive:** Preserves character fidelity and avoids downstream string-matching bugs.
- **Negative:** None — the encoding is confirmed from the source system.

---

## ADR 0005: Drift Monitor with Advisory Flagging Instead of Automatic Retraining

### Context
A drift monitor can either alert operators or autonomously trigger pipeline retraining.

### Decision
The drift monitor strictly logs findings and sets `drift_flagged = True`. It **never** auto-triggers retraining. Retraining is guided by `RETRAIN_POLICY.md` (requiring 3 consecutive weeks of drift or ground-truth accumulation, followed by economic validation).

### Alternative Considered
**Automatic retrain-on-flag** — trigger `src/train.py --promote` whenever the drift monitor sets `drift_flagged = True`.

### Why Rejected
Auto-retraining on a single anomalous week promotes a new model during the same operational event that caused the drift flag. If a sensor fault or data pipeline hiccup produces one week of unusual telemetry, auto-retraining learns from the artifact and the "new model" is worse than the old one — with no human review checkpoint to catch it. We demonstrated this exact failure in the `v2_broken` training cycle: a sigma=999 model was promoted and immediately failed `rollback verify`. The retrain policy's 3-consecutive-week threshold exists to separate real distributional shift from noise. Human sign-off before promotion is the control that makes rollback meaningful.

### Consequences
- **Positive:** Prevents retraining loops on noisy or transient single-week sensor anomalies.
- **Negative:** Requires human operational sign-off for trigger escalation.

---

## ADR 0006: What the System Cannot Do

### Current Limitations

1. **Intra-Week Real-Time Streaming:** The system operates on weekly batch increments (Mondays 00:00 UTC). It is not designed for sub-hour real-time telemetry streaming. A gateway that fails on Wednesday afternoon will not appear in rankings until the following Monday's run.
2. **Autonomous Physical Work Order Dispatch:** The system generates ranked visit candidates with explainable risk reasons. It does not interface directly with third-party ERP/field ticketing software without human review. The API produces a prioritized list; a human dispatcher decides which visits to schedule.
3. **Hardware Defect Repair Without Field Inspection:** Anomaly scoring identifies behavioral divergence — elevated offline duration, disconnection spikes, reboot counts. Root-cause confirmation (antenna fault, power issue, firmware corruption) still requires on-site technician diagnostic. The system answers *who to visit*, not *what is wrong*.
4. **New-Gateway Cold Start:** A gateway installed fewer than 24 hours before a prediction run has no per-gateway baseline statistics and is explicitly excluded from ranking (ADR 0007). A genuinely failing new gateway will not be caught until it accumulates sufficient history.
5. **Episode Re-detection After Visit:** The scoring model does not track which gateways have already been visited in the current fault episode. A gateway ranked #1 two weeks running may be the same ongoing fault, not a new one — re-visiting it wastes a €380 dispatch slot.

### What Two More Weeks Would Fix

Ranked by estimated impact on the €600/week cost metric:

1. **Episode tracking** (Week 1, high impact): Build a visit-history cache in `predict.py` so gateways already visited in the trailing N weeks are down-weighted rather than re-ranked identically. This directly targets the most expensive mistake available: re-dispatching to a gateway in the same continuous fault episode.
2. **Meter-read success integration** (Week 1, high impact): `data/meter_read_success.csv` records how many meters were read per gateway per week. A gateway with 60% meter read rate is already costing €600/week for unread meters. Incorporating this as a multiplicative weight on the anomaly score would prioritize gateways whose failures are already measurably costly — without requiring any additional data source.
3. **`POST /api/predictions/run` cache invalidation** (Week 1, medium impact): The API currently serves a pre-generated `predictions.csv`. After a new telemetry month arrives, the cached file is stale until regenerated by CLI. An automatic file-watcher or explicit `POST /api/predictions/run` endpoint would make the live API always reflect the latest data.
4. **Retrain on ground-truth feedback loop** (Week 2, high impact): The current retrain policy requires 3 consecutive drift flags. With two more weeks, we would collect field visit outcomes from the scored window, use `field_visits.outcome == "Fehler behoben"` as a weak positive label, and validate whether a supervised signal (logistic regression or XGBoost) beats the 3-sigma baseline on total cost — not just accuracy.

---

## ADR 0007: Deliberate Exclusion of New and Gone-Quiet Gateways

### Context
The 3-sigma scoring logic requires per-gateway historical statistics. A gateway with fewer than 24 hours in the baseline window produces an unreliable standard deviation (std from 1–23 points vs. 24×28=672 in the normal case). Two failure modes were identified during audit:
- **New gateway** (< 28 days history): baseline std is computed from too few points; flagging decisions would be spurious.
- **Gone-quiet gateway** (zero rows in the recent 7-day window): no recent observations means 0 flagged hours; the gateway simply scores 0.

### Decision
Gateways with fewer than `MIN_BASELINE_HOURS = 24` hours in the baseline window are **explicitly excluded** from scoring for that week. This is implemented in `rank_week()` via a count check before any stats are computed — not as a side-effect of NaN arithmetic from `fillna(False)`. The exclusion list is returned to `score_all_weeks()` which logs a `WARNING` for each excluded gateway. Gone-quiet gateways (zero recent rows but sufficient baseline) receive a score of 0 and fall below the top-15 cutoff naturally.

### Alternative Considered
**Global cross-gateway fallback std** — for gateways with short history, substitute a fleet-wide standard deviation computed from all gateways in that week's baseline window.

### Why Rejected
A global std conflates gateways with very different failure modes: a rural rooftop gateway with 40 meters served and a basement plant-room gateway with 900 meters have fundamentally different normal offline durations. Applying the same std to both would produce inconsistent flagging — urban gateways with naturally higher variance would be under-flagged, rural ones over-flagged. This is worse than exclusion because it produces confident-looking scores that are not reliable. Explicit exclusion with a logged warning surfaces the gap to operators; a spurious global-std score would be invisible.

### Consequences
- **Positive:** New gateway exclusion is auditable via log output. No spurious flags on gateways whose behavior is not yet characterized. NaN scores cannot appear in output.
- **Negative:** A genuinely faulty new gateway that fails within its first 24 hours will not be captured until it accumulates sufficient history. This is an acceptable operational trade-off documented here.

---

## ADR 0009: Gone-Quiet Gateways — Explicit Drift-Report Logging Rather Than Score Injection

### Context
The 3-sigma scoring model has a structural blind spot identified during submission review (FAQ 7.1): a gateway that goes completely silent — zero telemetry rows in the recent 7-day scoring window — contributes zero flagged hours, scores 0, and falls below rank 15. It cannot reach the top 15 by any mechanism within the current model.

This is the highest-urgency failure case in the entire problem: a completely dead gateway costs **€600/week** in unread meters. FAQ 7.1 states directly: *"A gateway that has gone quiet should not crash your pipeline or silently disappear from your ranking without you noticing."*

The existing `_check_gateway_population()` already computes `missing_gateway_ids` (gateways absent from the full telemetry directory). However it does not catch the real scenario: a gateway present in historical months but silent in the last 7 days — the parquet directory still contains it, so `known_ids - new_ids = ∅`. A separate recent-window check is required.

### Decision
Add `_check_silent_gateways()` to `src/drift_monitor.py`. For every `known_gateway_id` with zero rows in the last `SILENT_GATEWAY_RECENT_DAYS = 7` days, add it to a `silent_gateways` list in the `DriftReport` and log a `[WARN]` line to stdout. Surface the list via `GET /api/drift/status`.

This check does **NOT** set `drift_flagged = True`. It is advisory only — an operational signal for human review, not a data quality signal that should block prediction or increment the consecutive-flag retrain counter.

### Alternative Considered
**Score injection** — assign a fabricated maximum score to all silent gateways and force them into the top-15 ranking, treating total silence as the worst possible anomaly.

### Why Rejected
Total silence is operationally ambiguous. A gateway with zero recent rows could be:
1. **Hardware death** (power failure, antenna fault) — urgent, send a visit
2. **Data pipeline failure** (gateway is alive, telemetry not reaching the store) — a visit finds nothing wrong and wastes €380
3. **Silent decommission** (gateway removed, asset register not updated) — another wasted slot

Score injection treats all three identically. An operator with local knowledge can distinguish them; an algorithm cannot. FAQ 7.1's bar is *"without you noticing"* — not *"automatically in the top 15"*. The logging clears that bar without fabricating a score.

### Consequences
- **Positive:** FAQ 7.1 requirement satisfied. Gone-quiet gateways cannot disappear without being noticed. They appear in every drift report and API response (`GET /api/drift/status`).
- **Positive:** `drift_flagged` and the retrain counter are not affected. A batch with silent gateways is not inherently a data quality problem.
- **Positive:** The `silent_gateways` list gives the operations team an explicit "no recent telemetry" work queue — actionable without changing the scoring model.
- **Negative:** Silent gateways do not appear in `predictions.csv`. If asked "why isn't gateway X in the top 15?", the answer is: "zero telemetry in the last 7 days — check the drift report's `silent_gateways` field."
- **Negative:** The cutoff uses `pd.Timestamp.now(tz="UTC")`, anchored to when the drift monitor runs, not the prediction week boundary. Acceptable — the monitor is always run immediately before prediction.
