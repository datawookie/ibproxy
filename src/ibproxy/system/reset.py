import logging

import ibauth
from fastapi import APIRouter, HTTPException, Request

from ..models import SystemStatus
from .status import get_system_status

router = APIRouter()


@router.post(
    "",
    summary="Refresh connection to IBKR API",
    response_model=SystemStatus,
)  # type: ignore[untyped-decorator]
async def reset(request: Request) -> SystemStatus:
    """
    Build a fresh auth and replace the instance on app state so the tickle loop and proxy will immediately use it.
    """
    try:
        auth = ibauth.auth_from_yaml(request.app.state.args.config)
        request.app.state.auth = auth
        try:
            logging.info("🔀 Reset connection to IBKR API.")
            await auth.connect()
        except Exception:
            logging.error("🚨 Authentication failed!")
        else:
            logging.info("✅ Authentication succeeded.")

        return await get_system_status()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
