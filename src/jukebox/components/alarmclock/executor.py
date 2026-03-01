"""AlarmExecutor: state machine for a single firing alarm instance."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Literal

from .fade_in import FadeIn
from .models import AlarmActiveState, AlarmConfig, AlarmId, CardId

logger = logging.getLogger('jb.alarmclock.executor')

AlarmState = Literal['firing', 'snoozed', 'idle']


class AlarmExecutor:
    """Manages the fire → active → snoozed/idle lifecycle of a single alarm.

    All side effects are injected as callables for testability.
    The current state is tracked as an AlarmActiveState Pydantic model.
    """

    def __init__(self,
                 alarm_id: AlarmId,
                 alarm_cfg: AlarmConfig,
                 get_volume_fn: Callable[[], int],
                 set_volume_fn: Callable[[int], None],
                 stop_player_fn: Callable[[], None],
                 trigger_card_fn: Callable[[CardId], bool],
                 trigger_fallback_fn: Callable[[], None],
                 publish_fn: Callable[[AlarmActiveState], None]):
        """
        :param trigger_card_fn: Called with CardId. Returns True if card was found.
        :param trigger_fallback_fn: Called when card not found or content unavailable.
        :param publish_fn: Called with AlarmActiveState on state transitions.
        """
        self._alarm_id = alarm_id
        self._cfg = alarm_cfg
        self._get_volume = get_volume_fn
        self._set_volume = set_volume_fn
        self._stop_player = stop_player_fn
        self._trigger_card = trigger_card_fn
        self._trigger_fallback = trigger_fallback_fn
        self._publish = publish_fn

        self._active_state: AlarmActiveState = AlarmActiveState()
        self.pre_alarm_volume: int | None = None
        self._fade_in: FadeIn | None = None
        self._max_timer: threading.Timer | None = None

    @property
    def state(self) -> AlarmState:
        """Current state: 'firing', 'snoozed', or 'idle'."""
        return self._active_state.state or 'idle'

    def fire(self):
        """Execute alarm: save pre-alarm state, stop player, play content, fade in."""
        logger.info(f"Firing alarm '{self._alarm_id}' ('{self._cfg.label}')")

        # 1. Save pre-alarm volume
        self.pre_alarm_volume = self._get_volume()

        # 2. Stop current playback
        self._stop_player()

        # 3. Set start volume
        vol = self._cfg.volume
        self._set_volume(vol.start)

        # 4. Trigger content
        card_id = self._cfg.content.card_id
        if card_id:
            found = self._trigger_card(card_id)
            if not found:
                logger.warning(f"Card '{card_id}' not in database — using fallback")
                self._trigger_fallback()
        else:
            logger.info("No card_id configured — using fallback")
            self._trigger_fallback()

        # 5. Fade-in volume
        if vol.fade_in:
            self._fade_in = FadeIn(
                start=vol.start,
                target=vol.target,
                ramp_seconds=vol.ramp_seconds,
                steps=vol.steps,
                set_volume_fn=self._set_volume,
            )
            self._fade_in.start()

        # 6. Max-duration timer
        if self._cfg.max_duration:
            self._max_timer = threading.Timer(self._cfg.max_duration, self.dismiss)
            self._max_timer.daemon = True
            self._max_timer.start()

        self._set_state('firing')

    def dismiss(self):
        """Dismiss alarm and restore pre-alarm state."""
        logger.info(f"Dismissing alarm '{self._alarm_id}'")
        self._cancel_timers()

        if self._cfg.volume.restore_after and self.pre_alarm_volume is not None:
            self._set_volume(self.pre_alarm_volume)

        self.pre_alarm_volume = None
        self._set_state(None)

    def snooze(self) -> int:
        """Snooze alarm. Returns snooze duration in seconds."""
        duration = self._cfg.snooze_duration or 600
        logger.info(f"Snoozing alarm '{self._alarm_id}' for {duration}s")
        self._cancel_timers()
        self._set_state('snoozed')
        return duration

    def _set_state(self, state: Literal['firing', 'snoozed'] | None):
        self._active_state = AlarmActiveState(
            alarm_id=self._alarm_id if state is not None else None,
            state=state,
            label=self._cfg.label,
        )
        self._publish(self._active_state)

    def _cancel_timers(self):
        if self._fade_in and self._fade_in.is_alive():
            self._fade_in.cancel()
        if self._max_timer is not None:
            self._max_timer.cancel()
            self._max_timer = None
