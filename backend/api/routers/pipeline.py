"""
Pipeline router — training operations.

POLICY (see RETRAIN_POLICY.md):
  Training is a CLI-only, operator-controlled action. It must never be
  triggerable via HTTP during a live demo session or in production. This
  router exists to make the intent explicit: any attempt to POST /api/pipeline/train
  returns HTTP 501 Not Implemented with a clear policy message.

  To train a new version, use the CLI:
    python -m src.train --data <data_dir> --version <name> --promote
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])


@router.post("/train", status_code=501)
def train_model_disabled() -> JSONResponse:
    """
    Training is CLI-only by design; see RETRAIN_POLICY.md.

    This endpoint intentionally returns HTTP 501 Not Implemented.
    Triggering a training run via HTTP during a live session is an
    operational risk — it would block the request thread for minutes and
    could accidentally promote a new version mid-demo.

    Use the CLI instead:
      python -m src.train --data <data_dir> --version <name> [--promote]
    """
    return JSONResponse(
        status_code=501,
        content={
            "detail": (
                "Training is CLI-only by design; see RETRAIN_POLICY.md. "
                "Use: python -m src.train --data <data_dir> --version <name> [--promote]"
            )
        },
    )
