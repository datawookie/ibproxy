from datetime import UTC, datetime

from fastapi import APIRouter, Request

from .models import Uptime

router = APIRouter()


@router.get(
    "",
    summary="Proxy Uptime",
    description="How long has the proxy been running since last restart?",
    response_model=Uptime,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "started": "2025-09-24T04:20:33.894713",
                        "uptime_seconds": 90476.235,
                        "uptime_human": "1 day, 1:07:56.235000",
                    }
                }
            },
        },
    },
)  # type: ignore[misc]
async def status(request: Request) -> Uptime:
    uptime = datetime.now(UTC) - request.app.state.started_at

    return Uptime(
        started=request.app.state.started_at,
        uptime_seconds=uptime.total_seconds(),
        uptime_human=str(uptime),
    )
