"""Cancel gate — shared asyncio state for scheduler ↔ middleware communication.

The scheduler opens the gate before sending a "punch incoming" notification.
The cancel middleware closes it early if the user replies "取消".
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class CancelGate:
    """A one-shot gate that the scheduler opens and the user can close early.

    All methods must be called from the same asyncio event loop.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._active = False
        self._label = ""

    @property
    def active(self) -> bool:
        """True while a cancel window is open."""
        return self._active

    def open(self, label: str = "") -> None:
        """Open the cancel window and reset the event for a fresh wait."""
        self._active = True
        self._label = label
        self._event.clear()
        logger.debug("CancelGate opened: label=%r", label)

    def try_cancel(self) -> bool:
        """Attempt to cancel. Returns True if the gate was active."""
        if not self._active:
            return False
        self._event.set()
        logger.info("CancelGate cancelled: label=%r", self._label)
        return True

    async def wait_or_timeout(self, seconds: float) -> bool:
        """Wait up to `seconds`. Returns True if cancelled, False on timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=seconds)
            return True  # user cancelled
        except asyncio.TimeoutError:
            return False  # timed out → proceed with punch

    def close(self) -> None:
        """Close the cancel window after punch or cancellation."""
        self._active = False
        self._label = ""
        self._event.clear()
        logger.debug("CancelGate closed")
