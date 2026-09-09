# Architectural Decisions Log (ADR)
**LPDG Gateway Visit Prioritization (MLOps Track)**

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

### Consequences
- **Positive:** Full auditability, instant rollback via pointer swap, zero implicit compute during inference.
- **Negative:** Requires explicit promotion step (`--promote`).

---

## ADR 0002: File-Based Model Registry over External DB

### Context
The evaluation occurs in both automated grading and a live ~35-minute demonstration session. Dependency on external services (PostgreSQL, MLflow, AWS S3) introduces external failure modes, latency, and credential overhead.

### Decision
Implement a zero-infra, file-based model registry using `models/*.json`, a plain-text `models/ACTIVE` pointer file, and an append-only `models/rollback_log.jsonl` audit log.

### Consequences
- **Positive:** Inspectable with standard Unix tools (`cat`, `ls`), zero latency, 100% demo stability, safe inside containerized air-gapped environments.
- **Negative:** Limited concurrent write throughput (irrelevant for weekly batch cadence).

---

## ADR 0003: Single Normalization Boundary for Inconsistent Gateway Identifiers

### Context
Gateway IDs are represented as colon-separated MAC addresses (`06:5B:92:87:16:CD`) in asset/work-order registers, but bare hex strings (`065B928716CD`) in parquet telemetry. A naive join silently matches 0 rows without raising errors.

### Decision
Enforce bare uppercase hex normalization immediately upon data ingress in `src/load.py`. No downstream component handles colon formatting. `load_all()` asserts minimum cross-table ID overlap.

### Consequences
- **Positive:** Eliminates silent join failure bug classes across all consumers.
- **Negative:** Ingress validation overhead (amortized during load).

---

## ADR 0004: Explicit Latin-1 Ingress Decoding for German Asset Metadata

### Context
`gateway_master.csv` contains German geographic and infrastructure terms (e.g. `Außenmast`, `Baden-Württemberg`, `Schaltschrank`). Default UTF-8 reading corrupts strings into replacement characters silently.

### Decision
Specify `encoding="latin-1"` explicitly on `pd.read_csv` in `load_gateway_master()`.

### Consequences
- **Positive:** Preserves character fidelity and avoids downstream string-matching bugs.

---

## ADR 0005: Drift Monitor with Advisory Flagging Instead of Automatic Retraining

### Context
A drift monitor can either alert operators or autonomously trigger pipeline retraining.

### Decision
The drift monitor strictly logs findings and sets `drift_flagged = True`. It **never** auto-triggers retraining. Retraining is guided by `RETRAIN_POLICY.md` (requiring 3 consecutive weeks of drift or ground-truth accumulation, followed by economic validation).

### Consequences
- **Positive:** Prevents retraining loops on noisy or transient single-week sensor anomalies.
- **Negative:** Requires human operational sign-off for trigger escalation.

---

## ADR 0006: What the System Cannot Do

1. **Intra-Week Real-Time Streaming:** The system operates on weekly batch increments (Mondays 00:00 UTC). It is not designed for sub-hour real-time telemetry streaming.
2. **Autonomous Physical Work Order Dispatch:** The system generates ranked visit candidates with explainable risk reasons. It does not interface directly with third-party ERP/field ticketing software without human review.
3. **Hardware Defect Repair Without Field Inspection:** Anomaly scoring identifies behavioral divergence; root-cause confirmation requires on-site technician diagnostic.

---

## ADR 0007: Deliberate Exclusion of New and Gone-Quiet Gateways

### Context
The 3-sigma scoring logic requires per-gateway historical statistics. A gateway with fewer than 24 hours in the baseline window produces an unreliable standard deviation (std from 1–23 points vs. 24×28=672 in the normal case). Two failure modes were identified during audit:
- **New gateway** (< 28 days history): baseline std is computed from too few points; flagging decisions would be spurious.
- **Gone-quiet gateway** (zero rows in the recent 7-day window): no recent observations means 0 flagged hours; the gateway simply scores 0.

### Decision
Gateways with fewer than `MIN_BASELINE_HOURS = 24` hours in the baseline window are **explicitly excluded** from scoring for that week. This is implemented in `rank_week()` via a count check before any stats are computed — not as a side-effect of NaN arithmetic from `fillna(False)`. The exclusion list is returned to `score_all_weeks()` which logs a `WARNING` for each excluded gateway. Gone-quiet gateways (zero recent rows but sufficient baseline) receive a score of 0 and fall below the top-15 cutoff naturally.

### Consequences
- **Positive:** New gateway exclusion is auditable via log output. No spurious flags on gateways whose behavior is not yet characterized. NaN scores cannot appear in output.
- **Negative:** A genuinely faulty new gateway that fails within its first 24 hours will not be captured until it accumulates sufficient history. This is an acceptable operational trade-off documented here.
- **Alternative rejected:** Using a global (cross-gateway) fallback std for gateways with short history — rejected because this would conflate gateways with very different failure modes (rural vs. urban, 4G vs. 2G) and produce inconsistent flagging.
