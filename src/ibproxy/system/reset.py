import logging

from fastapi import APIRouter, HTTPException, Request
from ibauth import IBAuth
from starlette.datastructures import State
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from ..models import SystemStatus
from .status import get_system_status

router = APIRouter()


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=10))  # type: ignore[untyped-decorator]
async def _wait_for_disconnected(auth: IBAuth) -> None:
    status = await auth.status()
    if status.connected:
        raise ValueError("Session is still connected.")


async def _reconnect(state: State) -> SystemStatus:
    """
    Reconnect to the IBKR API by closing and reopening the connection.

    This function temporarily blocks new requests, closes the existing connection to IBKR,
    waits for disconnection, and then establishes a new connection. If successful, it returns
    the current system status. The request gate is always reopened to resume normal request
    processing.

    Args:
        state: An application state object containing:
            - gate: An asyncio.Event used to control request flow (clear to block, set to allow)
            - auth: An authentication/connection manager with logout() and connect() methods

    Returns:
        The result of get_system_status() if reconnection is successful.

    Raises:
        HTTPException: With status code 502 if a RuntimeError occurs during reconnection.
    """
    # Close the gate (block new requests).
    logging.warning("🚧 Stop processing new requests.")
    state.gate.clear()

    try:
        # Close existing connection.
        logging.warning("⛔ Close connection to IBKR API.")
        await state.auth.logout()
        logging.warning("⏳ Wait for session to disconnect.")
        try:
            await _wait_for_disconnected(state.auth)
        except RetryError:
            logging.warning("🚨 Failed to disconnect.")
        else:
            logging.info("✅ Disconnected.")

        logging.info("🔀 Connect to IBKR API.")
        await state.auth.connect()
        logging.info("✅ Connected.")

        return await get_system_status()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        # Open the gate (allow new requests).
        logging.warning("🚧 Resume processing new requests.")
        state.gate.set()


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

    return await _reconnect(request.app.state)
