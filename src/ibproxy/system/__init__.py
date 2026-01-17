"""System endpoints router module."""

from fastapi import APIRouter

from . import health, reset, status, uptime

router = APIRouter(tags=["system"])

# Include all system endpoint routers
router.include_router(status.router, prefix="/status")
router.include_router(reset.router, prefix="/reset")
router.include_router(uptime.router, prefix="/uptime")
router.include_router(health.router, prefix="/health")
