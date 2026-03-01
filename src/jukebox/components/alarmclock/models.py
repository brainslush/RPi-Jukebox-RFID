"""Pydantic v2 models for alarm clock configuration.

These models provide type safety and validation for all alarm data.
YAML ↔ model round-trip is supported via model_dump() and model_validate().

The `days` field in AlarmScheduleWeekly is a 7-element tuple of booleans,
one per weekday: (Mon, Tue, Wed, Thu, Fri, Sat, Sun).
"""

from __future__ import annotations

import datetime
from datetime import date
from datetime import time as Time
from pathlib import Path
from typing import Annotated, Literal, NewType, Optional, Tuple, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

AlarmId = NewType('AlarmId', str)
CardId = NewType('CardId', str)


def _system_timezone() -> str:
    """Return the IANA timezone name of the local system timezone, or 'UTC' as fallback."""
    try:
        local_tz = datetime.datetime.now().astimezone().tzinfo
        if hasattr(local_tz, 'key'):
            return local_tz.key
    except Exception:
        pass
    return 'UTC'


# ---------------------------------------------------------------------------
# Type alias for the 7-day weekday mask
# ---------------------------------------------------------------------------

# (Mon, Tue, Wed, Thu, Fri, Sat, Sun)
WeekdayMask = Tuple[bool, bool, bool, bool, bool, bool, bool]

_WEEKDAYS_MON_FRI: WeekdayMask = (True, True, True, True, True, False, False)


# ---------------------------------------------------------------------------
# Schedule models
# ---------------------------------------------------------------------------

class AlarmScheduleWeekly(BaseModel):
    """Recurring weekly alarm schedule.

    `days` is a 7-element tuple of booleans indexed Mon=0 … Sun=6.
    """

    type: Literal['weekly'] = 'weekly'
    days: WeekdayMask = _WEEKDAYS_MON_FRI
    end_date: Optional[date] = None

    model_config = {'extra': 'ignore'}


class AlarmScheduleOnce(BaseModel):
    """One-time alarm on a specific date."""

    type: Literal['once'] = 'once'
    date: date

    model_config = {'extra': 'ignore'}


# Union type for schedule — discriminated by 'type' field
AlarmSchedule = Annotated[
    Union[AlarmScheduleWeekly, AlarmScheduleOnce],
    Field(discriminator='type')
]


# ---------------------------------------------------------------------------
# Volume config
# ---------------------------------------------------------------------------

class AlarmVolumeConfig(BaseModel):
    """Volume settings for an alarm."""

    fade_in: bool = False
    start: Annotated[int, Field(ge=0, le=100)] = 0
    target: Annotated[int, Field(ge=0, le=100)] = 70
    restore_after: bool = True
    ramp_seconds: Annotated[float, Field(ge=1.0)] = 60.0
    steps: Annotated[int, Field(ge=1)] = 12

    model_config = {'extra': 'ignore'}


# ---------------------------------------------------------------------------
# Content config
# ---------------------------------------------------------------------------

class AlarmContentConfig(BaseModel):
    """Content (RFID card) to play for an alarm."""

    card_id: Optional[CardId] = None

    model_config = {'extra': 'ignore'}


# ---------------------------------------------------------------------------
# Main alarm config
# ---------------------------------------------------------------------------

class AlarmConfig(BaseModel):
    """Complete configuration for a single alarm."""

    label: str = ''
    time: Time = Time(7, 0)
    enabled: bool = True
    schedule: AlarmSchedule = Field(
        default_factory=lambda: AlarmScheduleWeekly()
    )
    content: AlarmContentConfig = Field(default_factory=AlarmContentConfig)
    volume: AlarmVolumeConfig = Field(default_factory=AlarmVolumeConfig)
    max_duration: Optional[Annotated[int, Field(ge=1)]] = None
    catch_up_window: Annotated[int, Field(ge=0)] = 300
    post_alarm: Literal['stop', 'resume'] = 'stop'
    snooze_duration: Optional[Annotated[int, Field(ge=60)]] = 600

    model_config = {'extra': 'ignore'}


# ---------------------------------------------------------------------------
# Settings models
# ---------------------------------------------------------------------------

class AlarmFallback(BaseModel):
    """Global fallback audio configuration."""

    card_id: Optional[CardId] = None
    file: Optional[Path] = None

    model_config = {'extra': 'ignore'}


class AlarmSettings(BaseModel):
    """Global alarm clock settings."""

    timezone: str = Field(default_factory=_system_timezone)
    fallback: AlarmFallback = Field(default_factory=AlarmFallback)

    model_config = {'extra': 'ignore'}


# ---------------------------------------------------------------------------
# Active alarm state (published via PubSub)
# ---------------------------------------------------------------------------

class AlarmActiveState(BaseModel):
    """Snapshot of an actively firing or snoozed alarm, suitable for PubSub."""

    alarm_id: AlarmId | None = None
    state: Literal['firing', 'snoozed'] | None = None
    label: str = ''

    model_config = {'extra': 'ignore'}
