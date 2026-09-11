# System Architecture — LPDG Gateway Prioritization
**MLOps Track · LPDG Selection Challenge 2026**

---

## High-Level Pipeline Architecture

```mermaid
flowchart TD
    subgraph DataIngress["Data Ingress Layer (src/load.py)"]
        A1[telemetry/*.parquet] --> L[load_all / load_telemetry]
        A2[gateway_master.csv] --> L
        A3[field_visits.csv] --> L
        A4[meter_read_success.csv] --> L
        L -->|Normalized bare hex IDs + Latin-1 decode| DF[Normalized DataFrames]
    end

    subgraph DriftMonitorLayer["Drift Monitoring (src/drift_monitor.py)"]
        DF --> DM[Run Drift Checks]
        DM -->|Check Schema, Population, Value Extremes| DR[drift_reports/YYYY-MM-DD.json]
        DR -->|3 consecutive flags| RP[RETRAIN_POLICY.md Guidelines]
    end

    subgraph TrainingRegistry["Training & Model Registry (src/train.py)"]
        DF --> TR[train.py --version vN]
        TR -->|Compute 3-sigma / Uplift Parameters| MR[models/vN_date.json]
        TR -.->|If --promote flag supplied| ACT[models/ACTIVE Pointer]
    end

    subgraph RollbackController["Rollback Engine (src/rollback.py)"]
        ACT --> RB[rollback.py to vN]
        RB -->|"Append (timestamp, from, to, reason)"| RBL[models/rollback_log.jsonl]
        RB -->|Swap Pointer| ACT
        ACT --> VB[rollback.py verify]
        VB -->|Check against stored fixed-slice hash| VRES[PASS / FAIL Output]
    end

    subgraph InferenceLayer["Deterministic Prediction (src/predict.py)"]
        ACT --> PR[predict.py --version ACTIVE]
        DF --> PR
        PR -->|Deterministic Sort & Rank 1..15| PRED[predictions.csv]
        PRED --> VAL[validate_submission.py]
        VAL -->|Exit Code 0| GATE[Grading Passed]
    end

    subgraph APIandDashboard["Presentation & API Layer (api/ + frontend/)"]
        ACT --> API[FastAPI backend]
        PRED --> API
        DR --> API
        RBL --> API
        API --> UI[React + TypeScript + Tailwind Dashboard]
    end
```

---

## Component Layout & Responsibilities

| Component | Path | Key Responsibility |
|---|---|---|
| Ingress Boundary | `src/load.py` | Id normalization (`06:5B:...` $\to$ `065B...`), Latin-1 decoding, schema invariant enforcement. |
| Model Training | `src/train.py` | Computes parameter artifacts, fixed-slice verification hashes, training data SHA-256 signatures. |
| Model Registry | `models/` | Plain-text `ACTIVE` pointer, versioned metadata `.json`, append-only audit trail `rollback_log.jsonl`. |
| Predictor | `src/predict.py` | Pure deterministic inference, formatted 120-row CSV generation compliant with `validate_submission.py`. |
| Drift Monitor | `src/drift_monitor.py` | Non-blocking schema, gateway population, and distribution anomaly reporting. |
| Rollback Engine | `src/rollback.py` | CLI and programmatic version swaps with cryptographic verification. |
| REST API | `api/` | High-performance FastAPI routers for registry, prediction delivery, drift status, and pipeline control. |
| Web Dashboard | `frontend/` | Interactive operations UI for telemetry drill-down, live rollback demo, and metric visualization. |
