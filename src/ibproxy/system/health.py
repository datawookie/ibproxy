from fastapi import APIRouter, Request

from ..models import Health

router = APIRouter()


@router.get(
    "",
    summary="Proxy Health Check",
    description="Retrieve the health status of the proxy.",
    response_model=Health,
)  # type: ignore[misc]
async def health(request: Request) -> Health:
    from ..main import auth

    result = {"status": "degraded"}
    if auth is not None:
        if not auth.authenticated:
            result = {"status": "not authenticated"}
        elif getattr(auth, "bearer_token", None):
            result = {"status": "ok"}

    return Health(**result)
