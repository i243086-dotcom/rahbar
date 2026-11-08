"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.readiness import check_readiness

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request) -> JSONResponse:
    """200 only when every dependency is usable; otherwise 503 naming the one that failed."""
    ready, checks = check_readiness(request.app.state)
    failed = [k for k, v in checks.items() if not v.startswith("ok")]
    body = {"status": "ready" if ready else "not ready", "checks": checks}
    if failed:
        body["failed"] = ", ".join(failed)
    return JSONResponse(body, status_code=200 if ready else 503)
