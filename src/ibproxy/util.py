import asyncio
import logging
import psutil
from pathlib import Path


def logging_level(logger: logging.Logger | None = None) -> int:
    """
    Print the current logging level and whether DEBUG is enabled.
    """
    logger = logger or logging.getLogger()

    return logger.getEffectiveLevel()


async def cpu_percent() -> float:
    """
    Return the current system-wide CPU utilization as a percentage.
    """
    return await asyncio.to_thread(psutil.cpu_percent, interval=1)


async def ram_percent() -> float:
    """
    Return the current system-wide RAM utilization as a percentage.
    """
    return await asyncio.to_thread(lambda: psutil.virtual_memory().percent)


async def swap_percent() -> float:
    """
    Return the current system-wide swap utilization as a percentage.
    """
    return await asyncio.to_thread(lambda: psutil.swap_memory().percent)


async def disk_percent(path: Path = Path("/")) -> float:
    """
    Return the current disk utilization for the given path as a percentage.
    """
    return await asyncio.to_thread(lambda: psutil.disk_usage(path).percent)