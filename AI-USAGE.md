# AI Usage Disclosure
**LPDG Innovation Hub Selection Challenge 2026**

---

## Overview & Methodology
This submission utilized AI assistance for iterative code generation, test scaffolding, and documentation synthesis under strict engineering oversight and verification.

---

## Specific Areas of AI Assistance

1. **Test Generation & Coverage Automation:**
   - Assisted in writing comprehensive parameterized pytest test fixtures for ID normalization, Latin-1 encoding edge-cases, and FastAPI route responses.
2. **Schema & Contract Definitions:**
   - Assisted in drafting Pydantic models for data interchange and OpenAPI schemas.
3. **Documentation Synthesis:**
   - Assisted in drafting Architecture Decision Records (ADRs) and Mermaid diagrams based on the architectural decisions implemented.

---

## Human Engineering Verification

- All mathematical anomaly calculations and 3-sigma baseline logic were verified directly against `baseline_3sigma.py`.
- Format contracts were validated with the official grader `validate_submission.py`.
- Determinism, rollback verification, and drift checks were confirmed with automated unit test suites in CI.

---

## Specific Case: AI Error Caught and Corrected

**Drift monitor range check was tautological (caught during code review):**
The initial AI-generated implementation of `drift_monitor._check_value_ranges()` computed `historical_max` from the *incoming batch itself*, then checked whether values in that same batch exceeded it. This is a self-referential comparison that could never flag anything — the batch's own max can never exceed itself.

The error was caught by reading the actual comparison logic, not just the test output (the test was passing because the test also used the same batch). The fix was to store `metric_maxima` at *training time* in the model artifact's `drift_reference` field, and compare incoming data against training-time maxima. This is now implemented in `train.py` and `drift_monitor.py`, and tested in `test_drift_monitor_reports_historical_range_breach` which injects a value 1000× above the training max.

