"""Alarm scheduling: recurrence calculation and background scheduler thread."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from functools import partial
from typing import Callable
from zoneinfo import ZoneInfo

from .models import AlarmConfig, AlarmId, AlarmScheduleOnce, AlarmScheduleWeekly

logger = logging.getLogger('jb.alarmclock.scheduler')

# Weekday index mapping: weekday() returns 0=Mon … 6=Sun, matching our WeekdayMask
# (Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6)


def next_fire_time(alarm: AlarmConfig, after_dt: datetime,
                   tz: ZoneInfo) -> datetime | None:
    """Calculate the next datetime this alarm should fire, strictly after `after_dt`.

    :param alarm: Validated AlarmConfig instance
    :param after_dt: Timezone-aware (or naive) datetime; next fire time is strictly after this
    :param tz: ZoneInfo for wall-clock time interpretation
    :return: Next fire datetime (timezone-aware, in `tz`) or None
    """
    if not alarm.enabled:
        return None

    hour = alarm.time.hour
    minute = alarm.time.minute

    # Ensure after_dt is in the alarm's timezone
    if after_dt.tzinfo is None:
        after_dt = after_dt.replace(tzinfo=tz)
    else:
        after_dt = after_dt.astimezone(tz)

    schedule = alarm.schedule

    if isinstance(schedule, AlarmScheduleOnce):
        fire_dt = datetime(
            schedule.date.year, schedule.date.month, schedule.date.day,
            hour, minute, tzinfo=tz
        )
        return fire_dt if fire_dt > after_dt else None

    elif isinstance(schedule, AlarmScheduleWeekly):
        days_mask = schedule.days
        if not any(days_mask):
            return None

        for delta_days in range(0, 8):
            candidate = after_dt + timedelta(days=delta_days)
            # Build wall-clock datetime for this candidate day (respects DST)
            fire_dt = datetime(
                candidate.year, candidate.month, candidate.day,
                hour, minute, tzinfo=tz
            )

            if fire_dt <= after_dt:
                continue

            if not days_mask[fire_dt.weekday()]:
                continue

            if schedule.end_date is not None and fire_dt.date() > schedule.end_date:
                return None

            return fire_dt

        return None

    else:
        logger.warning(f"Unknown schedule type: {type(schedule)}")
        return None


class AlarmScheduler:
    """Background thread that sleeps until the next alarm and fires it.

    Uses threading.Event.wait(timeout) for power-efficient sleeping.
    The thread wakes immediately on config changes via wakeup().
    """

    def __init__(
        self,
        alarms_getter: Callable[[],
        dict[AlarmId, AlarmConfig]],
        on_fire: Callable[[AlarmId, AlarmConfig], None],
        timezone: ZoneInfo,
        _now_fn: Callable[[], datetime] | None = None
    ):
        """
        :param alarms_getter: Zero-arg callable returning {alarm_id: AlarmConfig}
        :param on_fire: Called with (alarm_id, alarm_config) when alarm fires
        :param timezone: ZoneInfo for wall-clock time interpretation
        :param _now_fn: Injectable clock (defaults to datetime.now(tz)); for testing only
        """
        self._alarms_getter = alarms_getter
        self._on_fire = on_fire
        self._tz = timezone
        self._now_fn = _now_fn if _now_fn is not None else partial(datetime.now, timezone)
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name='AlarmClockScheduler'
        )

    def start(self):
        """Start the background scheduler thread."""
        logger.info("AlarmScheduler starting")
        self._thread.start()

    def stop(self):
        """Stop the scheduler thread (blocks until it exits, max 5s)."""
        logger.info("AlarmScheduler stopping")
        self._stop.set()
        self._wakeup.set()
        self._thread.join(timeout=5)

    def wakeup(self):
        """Wake the scheduler to recalculate next fire time immediately.

        Call this whenever alarms are added, updated, or deleted.
        """
        self._wakeup.set()

    def _find_next(self) -> tuple[AlarmId | None, AlarmConfig | None, datetime | None]:
        """Find the alarm with the earliest upcoming fire time."""
        now = self._now_fn()
        alarms = self._alarms_getter()
        next_id: AlarmId | None = None
        next_cfg: AlarmConfig | None = None
        next_dt: datetime | None = None

        for alarm_id, alarm_cfg in alarms.items():
            fire_dt = next_fire_time(alarm_cfg, now, self._tz)
            if fire_dt is not None and (next_dt is None or fire_dt < next_dt):
                next_dt = fire_dt
                next_id = alarm_id
                next_cfg = alarm_cfg

        return next_id, next_cfg, next_dt

    def _run(self):
        """Main scheduler loop."""
        logger.debug("AlarmScheduler thread started")
        while not self._stop.is_set():
            self._wakeup.clear()
            alarm_id, alarm_cfg, fire_dt = self._find_next()

            if alarm_id is None or alarm_cfg is None or fire_dt is None:
                logger.debug("No pending alarms — sleeping indefinitely")
                self._wakeup.wait()
                continue

            now = self._now_fn()
            sleep_seconds = (fire_dt - now).total_seconds()
            logger.debug(
                f"Next alarm '{alarm_id}' in {sleep_seconds:.1f}s at {fire_dt.isoformat()}"
            )

            if sleep_seconds > 0:
                self._wakeup.wait(timeout=sleep_seconds)

            if self._stop.is_set():
                break

            if self._wakeup.is_set():
                # Config changed while sleeping — recalculate
                continue

            # Check catch-up window
            now = self._now_fn()
            elapsed = (now - fire_dt).total_seconds()
            catch_up = alarm_cfg.catch_up_window

            if elapsed <= catch_up:
                logger.info(f"Firing alarm '{alarm_id}' ('{alarm_cfg.label}')")
                try:
                    self._on_fire(alarm_id, alarm_cfg)
                except Exception:
                    logger.exception(f"Error in on_fire callback for '{alarm_id}'")
            else:
                logger.warning(
                    f"Missed alarm '{alarm_id}' by {elapsed:.0f}s "
                    f"(catch_up_window={catch_up}s) — skipping"
                )

        logger.debug("AlarmScheduler thread stopped")
