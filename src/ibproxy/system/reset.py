import logging

from fastapi import APIRouter, HTTPException, Request
from ibauth import IBAuth
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from ..models import SystemStatus
from .status import get_system_status

router = APIRouter()


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=10))  # type: ignore[untyped-decorator]
async def _wait_for_disconnected(auth: IBAuth) -> None:
    status = await auth.status()
    if status.connected:
        raise ValueError("Session is still connected.")


@router.post(
    "",
    summary="Refresh connection to IBKR API",
    response_model=SystemStatus,
)  # type: ignore[untyped-decorator]
async def reset(request: Request) -> SystemStatus:
    """
    Build a fresh auth and replace the instance on app state so the tickle loop and proxy will
    immediately use it.

    While the reset is taking place new requests will be blocked. This is important because these
    requests seem to disrupt the connection process.
    """
    # Close the gate (block new requests).
    logging.warning("🚧 Stop processing new requests.")
    request.app.state.gate.clear()

    try:
        # Close existing connection.
        logging.warning("⛔ Close connection to IBKR API.")
        await request.app.state.auth.logout()
        logging.warning("⏳ Wait for session to disconnect.")
        try:
            await _wait_for_disconnected(request.app.state.auth)
        except RetryError:
            logging.warning("🚨 Failed to disconnect.")
        else:
            logging.info("✅ Disconnected.")

        logging.info("🔀 Connect to IBKR API.")
        await request.app.state.auth.connect()
        logging.info("✅ Connected.")

        return await get_system_status()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        # Open the gate (allow new requests).
        logging.warning("🚧 Resume processing new requests.")
        request.app.state.gate.set()
