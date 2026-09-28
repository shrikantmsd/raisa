from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/readiness")
def readiness() -> dict:
    return {"status": "ready"}


@router.get("/health/liveness")
def liveness() -> dict:
    return {"status": "alive"}
