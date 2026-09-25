from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.container import Container
from api.deps import get_container

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up and serving."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(container: Container = Depends(get_container)) -> JSONResponse:
    """Readiness: every dependency the API needs answers. 503 until then, so
    an orchestrator does not route traffic to an instance that cannot serve."""
    results: dict[str, bool] = {}
    for name, check in container.readiness_checks.items():
        try:
            results[name] = bool(await check())
        except Exception:  # noqa: BLE001 - any failure means not ready
            results[name] = False
    ok = all(results.values())
    return JSONResponse(
        status_code=200 if ok else 503, content={"status": "ready" if ok else "degraded", **results}
    )
