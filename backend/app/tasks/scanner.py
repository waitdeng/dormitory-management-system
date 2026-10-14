"""Background reservation-expiry / alert scanner (M4).

Runs inside the FastAPI process on an interval. Safe to run concurrently with
API traffic: scanners re-check state under row locks and are idempotent.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_task: asyncio.Task | None = None
_stop = asyncio.Event()


async def _loop(interval_seconds: float) -> None:
    from app.core.database import AsyncSessionLocal
    from app.services import scanner_service

    while not _stop.is_set():
        try:
            async with AsyncSessionLocal() as db:
                result = await scanner_service.run_all_scans(db)
            logger.info(
                "scanner tick: expired=%s alerts=%s",
                result.get("expiry", {}).get("scanned"),
                result.get("alerts", {}).get("count"),
            )
        except Exception:  # noqa: BLE001 — scanner must never kill the app
            logger.exception("scanner tick failed; will retry")
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(_stop.wait(), timeout=interval_seconds)


def start_background_scanner(interval_seconds: float | None = None) -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _stop.clear()
    interval = interval_seconds or float(getattr(settings, "SCANNER_INTERVAL_SECONDS", 60))
    _task = asyncio.get_event_loop().create_task(_loop(interval))
    logger.info("background scanner started (interval=%ss)", interval)


async def stop_background_scanner() -> None:
    global _task
    _stop.set()
    if _task is not None:
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(_task, timeout=5)
        _task = None
