"""Pydantic v2 models for alarm clock configuration.

These models provide type safety and validation for all alarm data.
YAML ↔ model round-trip is supported via model_dump() and model_validate().

The `days` field in AlarmScheduleWeekly is a 7-element tuple of booleans,
one per weekday: (Mon, Tue, Wed, Thu, Fri, Sat, Sun).
"""

from __future__ import annotations

from datetime import date
from datetime import time as Time
from pathlib import Path
from typing import Annotated, Literal, NewType, Optional, Tuple, Union

from pydantic import BaseModel, Field

AlarmId = NewType('AlarmId', str)
CardId = NewType('CardId', str)


# (Mon, Tue, Wed, Thu, Fri, Sat, Sun)
WeekdayMask = Tuple[bool, bool, bool, bool, bool, bool, bool]
_WEEKDAYS_MON_FRI: WeekdayMask = (True, True, True, True, True, False, False)


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


class AlarmVolumeFadeInConfig(BaseModel):
    """Volume settings for an alarm."""

    mode: Literal["fadein"] = "fadein"
    start: Annotated[int, Field(ge=0, le=100)] = 0
    target: Annotated[int, Field(ge=0, le=100)] = 70
    restore_after: bool = True
    ramp_seconds: Annotated[float, Field(ge=1.0)] = 60.0
    steps: Annotated[int, Field(ge=1)] = 12


class AlarmVolumeConstantConfig(BaseModel):
    """Volume settings for a constant volume alarm"""

    mode: Literal["constant"] = "constant"
    volume: Annotated[int, Field(ge=0, le=100)] = 70
    restore_after: bool = True


AlarmVolumeConfig = Annotated[AlarmVolumeFadeInConfig | AlarmVolumeConstantConfig, Field(discriminator="mode")]


class AlarmContentConfig(BaseModel):
    """Content (RFID card) to play for an alarm."""

    card_id: Optional[CardId] = None


class AlarmConfig(BaseModel):
    """Complete configuration for a single alarm."""

    label: str = ''
    time: Time = Time(7, 0)
    enabled: bool = True
    schedule: AlarmSchedule = Field(
        default_factory=lambda: AlarmScheduleWeekly()
    )
    content: AlarmContentConfig = Field(default_factory=AlarmContentConfig)
    volume: AlarmVolumeConfig = Field(default_factory=AlarmVolumeConstantConfig)
    max_duration: Optional[Annotated[int, Field(ge=1)]] = None
    catch_up_window: Annotated[int, Field(ge=0)] = 300
    post_alarm: Literal['stop', 'resume'] = 'stop'
    snooze_duration: Optional[Annotated[int, Field(ge=60)]] = 600


class AlarmFallback(BaseModel):
    """Global fallback audio configuration."""

    card_id: Optional[CardId] = None
    file: Optional[Path] = None

    model_config = {'extra': 'ignore'}


class AlarmSettings(BaseModel):
    """Global alarm clock settings."""

    fallback: AlarmFallback = Field(default_factory=AlarmFallback)

    model_config = {'extra': 'ignore'}


class AlarmActiveState(BaseModel):
    """Snapshot of an actively firing or snoozed alarm, suitable for PubSub."""

    alarm_id: AlarmId | None = None
    state: Literal['firing', 'snoozed'] | None = None
    label: str = ''

    model_config = {'extra': 'ignore'}
