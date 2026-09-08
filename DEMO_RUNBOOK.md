# Live Demonstration Runbook

Use this runbook with the real dataset mounted at `./data`. It is designed to
demonstrate the mandatory submission gate and the MLOps-track controls without
changing raw data or requiring external services.

## 1. Produce and validate the submission

```bash
cd backend
python -m src.train --data ../data --version demo_v1 --promote
python -m src.drift_monitor --data ../data --reports-dir ../drift_reports
python -m src.predict --data ../data --out predictions.csv
python /path/to/validate_submission.py predictions.csv
```

Expected result: the validator exits with code `0`; `predictions.csv` has 120
rows and the columns `week_start,rank,gateway_id,score,reason`.

## 2. Demonstrate a schema-drift flag safely

Use a disposable copy of `data`, rename one telemetry column, and run:

```bash
python -m src.drift_monitor --data ../data-schema-drift --reports-dir ../drift_reports-demo
```

Expected result: a drift report naming the missing and/or new column. The
monitor records the event; it does not retrain or promote a model.

## 3. Demonstrate rollback

```bash
python -m src.rollback current
python -m src.train --data ../data --version demo_broken --sigma 999 --promote
python -m src.rollback to demo_v1_YYYY-MM-DD --reason "Demonstration: sigma=999 produces degenerate anomaly scores"
python -m src.rollback verify --data ../data
```

Replace `demo_v1_YYYY-MM-DD` with the version printed after training. Expected
result: verification reports `PASS` and the rollback audit log contains the
reason, source version, target version, and timestamp.
