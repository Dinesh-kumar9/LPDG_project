# LPDG Gateway Visit Prioritization (MLOps Track)
**LPDG Innovation Hub Selection Challenge 2026**

[![CI Pipeline](https://github.com/Dinesh-kumar9/LPDG_project/actions/workflows/ci.yml/badge.svg)](https://github.com/Dinesh-kumar9/LPDG_project/actions)
[![Coverage](https://img.shields.io/badge/coverage-78.6%25-brightgreen.svg)](https://github.com/Dinesh-kumar9/LPDG_project)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://reactjs.org/)

---

## 1. Problem Statement & Economics

LPDG operates a telemetry relay network of ~320 radio gateways for utility meter collection. Gateways experience silent degradation and fail without immediate notification. Field operations are constrained by a **hard cap of 15 site visits per week**.

**Cost Structure:**
| Event | Economic Impact |
|---|---|
| Visit finds a real fault | **+€600 / week** saved until repaired |
| Visit finds nothing (false alarm) | **-€380** wasted technician dispatch |
| Broken gateway left alone | **-€600 / week** repeating loss |

Historical baseline hit rate was ~34.7% (60.7% wasted visits). This system provides an **auditable, deterministic, MLOps-governed prioritization engine** to optimize technician dispatch decisions across 8 scored weeks (2 Feb – 23 Mar 2026).

---

## 2. Architecture & MLOps Components

```
Raw Data Ingress (Parquet + CSV + Excel)
   │
   ▼
[src/load.py] ─────────────► [src/drift_monitor.py]
  • ID normalization to bare hex    • Pre-inference schema check
  • Latin-1 German string decode    • Population & distribution monitor
  • Schema invariant assertions     • Logs to drift_reports/
   │
   ▼
[src/train.py]
  • Versioned parameter extraction
  • Cryptographic training data hash
  • Fixed-slice verification hash
   │
   ▼
[models/ Registry] ◄──────── [src/rollback.py]
  • vN_<date>.json                  • Atomic ACTIVE pointer flip
  • ACTIVE pointer                  • Cryptographic hash verification
  • rollback_log.jsonl audit        • Append-only rollback audit log
   │
   ▼
[src/predict.py]
  • Pure deterministic inference
  • Generates 120-row predictions.csv
  • Validated by validate_submission.py (Exit code 0)
   │
   ▼
[FastAPI Backend + React Operations Dashboard]
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed Mermaid diagrams and component contracts.

---

## 3. Quick Start

### Option A: One-Command Pipeline & Dashboard (Docker)
```bash
docker compose up
```
- Dashboard UI: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

### Option B: Step-by-Step CLI Execution
```bash
cd backend

# 1. Train model v1 and promote to ACTIVE
python -m src.train --data "../path/to/data" --version v1 --promote

# 2. Run pre-inference drift check
python -m src.drift_monitor --data "../path/to/data"

# 3. Generate deterministic predictions.csv (120 rows)
python -m src.predict --data "../path/to/data" --out predictions.csv

# 4. Validate output format against official grader
python "../path/to/validate_submission.py" predictions.csv
```

---

## 4. Live Session Rollback Demo (Under 60 Seconds)

During live evaluation, the system demonstrates instant rollback and cryptographic verification:

```bash
# 1. Inspect current active version
python -m src.rollback current
# Output: v1_2026-08-31

# 2. Train an experimental/broken candidate (e.g. sigma=999) and promote
python -m src.train --data "../path/to/data" --version v2_broken --sigma 999 --promote

# 3. Rollback immediately to v1 with operational audit reason
python -m src.rollback to v1_2026-08-31 --reason "v2 produced degenerate rankings"

# 4. Verify cryptographic hash match on fixed historical slice
python -m src.rollback verify --data "../path/to/data"
# Output: [OK] PASS -- v1_2026-08-31 produces byte-identical output to training time.
```

---

## 5. Repository Layout

```
├── backend/
│   ├── src/
│   │   ├── load.py               # Single normalization boundary
│   │   ├── train.py              # Versioned training & artifact creation
│   │   ├── predict.py            # Deterministic inference engine
│   │   ├── drift_monitor.py      # Non-blocking drift detection
│   │   └── rollback.py           # Registry controller & verification
│   ├── api/                      # High-performance FastAPI routers
│   ├── models/                   # Model registry (JSON + ACTIVE + audit log)
│   ├── tests/                    # Pytest suite (17 tests, >78% coverage)
│   └── pyproject.toml
├── frontend/                     # React 18 + TypeScript + Tailwind operations UI
├── drift_reports/                # Stored JSON drift monitor outputs
├── RETRAIN_POLICY.md             # Defensible operational retraining criteria
├── DECISIONS.md                  # Architectural Decision Records (ADRs)
├── ARCHITECTURE.md               # Visual system diagrams
├── AI-USAGE.md                   # Disclosure of AI tooling assistance
└── docker-compose.yml
```

---

## 6. Testing & Quality Assurance

- **17/17 Unit & Integration Tests Passed**
- **78.58% Test Coverage** (exceeds 75% gate)
- **Zero data files committed** (mounted read-only at runtime)
