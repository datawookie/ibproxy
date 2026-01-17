import logging

import ibauth
from fastapi import APIRouter, HTTPException, Request

from .models import SystemStatus
from .status import get_system_status

router = APIRouter()


@router.post(
    "",
    summary="Refresh connection to IBKR API",
    response_model=SystemStatus,
)  # type: ignore[misc]
async def reset(request: Request) -> SystemStatus:
    try:
        print(request.app.state.args.config)
        auth = ibauth.auth_from_yaml(request.app.state.args.config)
        try:
            await auth.connect()
        except Exception:
            logging.error("🚨 Authentication failed!")

        return await get_system_status()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
