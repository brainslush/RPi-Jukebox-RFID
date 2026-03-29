"""Volume fade-in for alarm clock activation."""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger('jb.alarmclock.fadein')


class FadeIn:
    """
    Ramps volume linearly from `start` to `target` over `ramp_seconds` in `steps` steps.

    Designed to be used with AlarmVolumeConfig. Can run synchronously
    (run_sync) or in a background thread (start/cancel).
    """

    def __init__(self, start: int, target: int, ramp_seconds: float,
                 steps: int, set_volume_fn: Callable[[int], None]):
        self._start = max(0, min(100, start))
        self._target = max(0, min(100, target))
        self._ramp_seconds = ramp_seconds
        self._steps = max(1, steps)
        self._set_volume = set_volume_fn
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def _volume_at_step(self, step: int) -> int:
        if self._steps == 1:
            return self._target
        ratio = step / (self._steps - 1)
        return max(0, min(100, round(self._start + ratio * (self._target - self._start))))

    def run_sync(self):
        """Run the fade-in synchronously. Blocks until complete or cancelled."""
        step_delay = self._ramp_seconds / self._steps
        for step in range(self._steps):
            if self._cancel.is_set():
                logger.debug("FadeIn cancelled")
                return
            self._set_volume(self._volume_at_step(step))
            if step < self._steps - 1:
                self._cancel.wait(timeout=step_delay)

    def start(self):
        """Start fade-in in a background thread."""
        self._cancel.clear()
        self._thread = threading.Thread(target=self.run_sync, daemon=True,
                                        name='AlarmFadeIn')
        self._thread.start()

    def cancel(self):
        """Cancel an in-progress fade-in."""
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
