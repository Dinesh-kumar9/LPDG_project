"""
LPDG Gateway Visit Prioritization — Core Pipeline Package.

Modules:
  load.py         — Single normalization boundary: gateway ID format unification,
                    Latin-1 decoding, schema invariant enforcement.
  train.py        — Versioned model artifact creation with cryptographic hashes.
  predict.py      — Deterministic 120-row CSV inference from a named registry version.
  drift_monitor.py — Non-blocking schema, population, and distribution drift detection.
  rollback.py     — Registry controller: list / current / to / verify commands.
"""
