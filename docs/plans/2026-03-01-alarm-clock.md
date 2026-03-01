# Alarm Clock Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an alarm clock component to RPi-Jukebox-RFID v3 that fires RFID card actions at scheduled times via a power-efficient sleeping thread, using Pydantic v2 models for type-safe alarm configuration.

**Architecture:** A new `alarmclock` plugin (`src/jukebox/components/alarmclock/`) follows the same plugin pattern as `timers/`. Pydantic v2 models define the alarm schema with validation. Alarms are stored in `shared/settings/alarmclock.yaml` (serialized via `model.model_dump()`). A daemon thread sleeps via `threading.Event.wait(timeout)` until the next alarm. All control is exposed via `@plugs.register` RPC endpoints.

**Tech Stack:** Python 3.9+, `pydantic>=2.0` (new dep), stdlib `threading`/`datetime`/`zoneinfo`, existing `plugs`/`cfghandler`/`publishing` infrastructure, React + MUI + i18next frontend.

**Design doc:** `docs/plans/2026-03-01-alarm-clock-design.md`

---

## Quick Reference

### How to run backend tests
```bash
cd /home/brainslush/gitprojects/RPi-Jukebox-RFID
python -m pytest test/alarmclock/ -v
```

### Plugin system basics
```python
import jukebox.plugs as plugs

@plugs.register          # exposes as RPC: <package>.<function_name>()
def my_function(): ...

@plugs.finalize          # runs after all plugins loaded
def finalize(): ...

@plugs.atexit            # runs on shutdown
def atexit(**ignored_kwargs): ...

# Call another plugin:
plugs.call_ignore_errors('player', 'ctrl', 'stop')
plugs.call('volume', 'ctrl', 'get_volume')
```

### Publishing state
```python
import jukebox.publishing as publishing
publishing.get_publisher().send('alarmclock.active', {'state': 'firing', ...})
```

### Execute a card's command
```python
import jukebox.utils as utils
import jukebox.cfghandler

cfg_cards = jukebox.cfghandler.get_handler('cards')
card_cmd = cfg_cards.getn(card_id)              # returns card's YAML config dict
utils.decode_and_call_rpc_command(card_cmd)     # decodes alias + calls via plugs
```

### Config access
```python
import jukebox.cfghandler
cfg = jukebox.cfghandler.get_handler('alarmclock')
cfg.load('/path/to/alarmclock.yaml')
cfg.setndefault('settings', 'timezone', value='UTC')
with cfg:                                        # thread-safe write
    cfg['alarms']['alarm_001'] = model.model_dump()
    cfg.save()
```

### Pydantic v2 patterns used in this codebase
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal

class MyModel(BaseModel):
    field: str = Field(default='value')

    model_config = {'extra': 'ignore'}   # silently ignore unknown keys from YAML

# Validate from dict (e.g. from YAML):
m = MyModel.model_validate(some_dict)

# Serialize to plain dict for YAML storage:
d = m.model_dump()
```

---

## Task 1: Add Pydantic dependency and plugin scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `src/jukebox/components/alarmclock/__init__.py`
- Create: `resources/default-settings/alarmclock.default.yaml`
- Modify: `resources/default-settings/jukebox.default.yaml`
- Create: `test/alarmclock/__init__.py`
- Create: `test/alarmclock/test_scaffold.py`

**Step 1: Write the failing test**

Create `test/alarmclock/__init__.py` (empty).

Create `test/alarmclock/test_scaffold.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('src/jukebox'))


def test_pydantic_importable():
    """pydantic v2 is installed"""
    import pydantic
    assert int(pydantic.VERSION.split('.')[0]) >= 2


def test_alarmclock_module_importable():
    """alarmclock plugin module can be imported"""
    import components.alarmclock
    assert components.alarmclock is not None
```

**Step 2: Run to verify pydantic test fails**

```bash
cd /home/brainslush/gitprojects/RPi-Jukebox-RFID
python -m pytest test/alarmclock/test_scaffold.py::test_pydantic_importable -v
```
Expected: FAIL if pydantic is not installed

**Step 3: Add pydantic to requirements.txt**

In `requirements.txt`, after the `ruamel.yaml` line, add:
```
pydantic>=2.0
```

**Step 4: Install pydantic**

```bash
pip install "pydantic>=2.0"
```
Expected: Successfully installed pydantic-2.x.x

**Step 5: Create the default YAML config**

Create `resources/default-settings/alarmclock.default.yaml`:

```yaml
# RPi-Jukebox-RFID Alarm Clock default settings
settings:
  # Timezone for wall-clock alarm time interpretation
  # Use any IANA timezone name, e.g. 'Europe/Berlin', 'America/New_York', 'UTC'
  timezone: UTC
  # Global fallback audio when alarm content is unavailable
  # card_id takes priority over file if both are set
  fallback:
    card_id: null
    file: null
alarms: {}
```

**Step 6: Create the plugin scaffold**

Create `src/jukebox/components/alarmclock/__init__.py`:

```python
# RPi-Jukebox-RFID Version 3
# Copyright (c) See file LICENSE in project root folder
"""Alarm Clock Plugin

Schedules audio playback at specific times using RFID card actions.
Alarms are stored in shared/settings/alarmclock.yaml.
Configuration is validated using Pydantic v2 models.
"""

import logging
import jukebox.cfghandler
import jukebox.plugs as plugs

logger = logging.getLogger('jb.alarmclock')
cfg = jukebox.cfghandler.get_handler('alarmclock')
cfg_main = jukebox.cfghandler.get_handler('jukebox')


@plugs.finalize
def finalize():
    config_file = cfg_main.setndefault(
        'alarmclock', 'config_file',
        value='../../shared/settings/alarmclock.yaml'
    )
    try:
        cfg.load(config_file)
    except FileNotFoundError:
        cfg.config_dict({'settings': {'timezone': 'UTC',
                                      'fallback': {'card_id': None, 'file': None}},
                         'alarms': {}})
        logger.warning(f"Alarm config not found, created empty: '{config_file}'")
        cfg.save(only_if_changed=False)

    cfg.setndefault('settings', 'timezone', value='UTC')
    cfg.setndefault('settings', 'fallback', 'card_id', value=None)
    cfg.setndefault('settings', 'fallback', 'file', value=None)
    logger.info("Alarm clock plugin initialized")


@plugs.atexit
def atexit(**ignored_kwargs):
    cfg.save(only_if_changed=True)
    return []
```

**Step 7: Add alarmclock to jukebox.default.yaml**

In `resources/default-settings/jukebox.default.yaml`:

1. In the `modules.named` section, after `timers: timers`, add:
   ```yaml
       alarmclock: alarmclock
   ```

2. At the bottom of the file, add:
   ```yaml
   alarmclock:
     config_file: ../../shared/settings/alarmclock.yaml
   ```

**Step 8: Run all scaffold tests**

```bash
python -m pytest test/alarmclock/test_scaffold.py -v
```
Expected: All PASS

**Step 9: Commit**

```bash
git add requirements.txt \
        src/jukebox/components/alarmclock/__init__.py \
        resources/default-settings/alarmclock.default.yaml \
        resources/default-settings/jukebox.default.yaml \
        test/alarmclock/__init__.py \
        test/alarmclock/test_scaffold.py
git commit -m "feat(alarmclock): add plugin scaffold, pydantic dependency, and default config"
```

---

## Task 2: Pydantic models for alarm configuration

**Files:**
- Create: `src/jukebox/components/alarmclock/models.py`
- Create: `test/alarmclock/test_models.py`

**Step 1: Write the failing tests**

Create `test/alarmclock/test_models.py`:

```python
import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import pytest
from datetime import date
from pydantic import ValidationError
from components.alarmclock.models import (
    AlarmConfig,
    AlarmScheduleWeekly,
    AlarmScheduleOnce,
    AlarmVolumeConfig,
    AlarmSettings,
    AlarmFallback,
)


# --- Schedule models ---

def test_weekly_schedule_valid():
    s = AlarmScheduleWeekly(days=['mon', 'wed', 'fri'])
    assert s.days == ['mon', 'wed', 'fri']
    assert s.end_date is None


def test_weekly_schedule_invalid_day():
    with pytest.raises(ValidationError):
        AlarmScheduleWeekly(days=['monday'])  # must use 3-letter abbreviations


def test_weekly_schedule_end_date_as_string():
    s = AlarmScheduleWeekly(days=['mon'], end_date='2030-06-01')
    assert s.end_date == date(2030, 6, 1)


def test_once_schedule_valid():
    s = AlarmScheduleOnce(date='2030-01-15')
    assert s.date == date(2030, 1, 15)


def test_once_schedule_invalid_date():
    with pytest.raises(ValidationError):
        AlarmScheduleOnce(date='not-a-date')


# --- Volume config ---

def test_volume_config_defaults():
    v = AlarmVolumeConfig()
    assert v.fade_in is False
    assert 0 <= v.start <= 100
    assert 0 <= v.target <= 100
    assert v.restore_after is True


def test_volume_config_clamps():
    with pytest.raises(ValidationError):
        AlarmVolumeConfig(start=150)  # out of range


# --- AlarmConfig ---

def test_alarm_config_weekly():
    alarm = AlarmConfig(
        time='07:30',
        schedule=AlarmScheduleWeekly(days=['mon', 'tue']),
        content={'card_id': '1234'},
    )
    assert alarm.enabled is True
    assert alarm.time == '07:30'
    assert alarm.post_alarm == 'stop'


def test_alarm_config_once():
    alarm = AlarmConfig(
        time='08:00',
        schedule=AlarmScheduleOnce(date='2030-01-01'),
        content={'card_id': '5678'},
    )
    assert alarm.schedule.date.year == 2030


def test_alarm_config_invalid_time():
    with pytest.raises(ValidationError):
        AlarmConfig(
            time='25:00',  # invalid hour
            schedule=AlarmScheduleWeekly(days=['mon']),
            content={'card_id': '1'},
        )


def test_alarm_config_invalid_post_alarm():
    with pytest.raises(ValidationError):
        AlarmConfig(
            time='07:00',
            schedule=AlarmScheduleWeekly(days=['mon']),
            content={'card_id': '1'},
            post_alarm='invalid_value',
        )


def test_alarm_config_roundtrip():
    """model_dump() → model_validate() preserves all fields"""
    alarm = AlarmConfig(
        label='Morning',
        time='07:00',
        schedule=AlarmScheduleWeekly(days=['mon', 'fri'], end_date='2030-12-31'),
        content={'card_id': '999'},
        volume=AlarmVolumeConfig(fade_in=True, start=10, target=80),
        max_duration=3600,
        catch_up_window=300,
        post_alarm='resume',
        snooze_duration=600,
    )
    d = alarm.model_dump()
    alarm2 = AlarmConfig.model_validate(d)
    assert alarm2.label == 'Morning'
    assert alarm2.volume.fade_in is True
    assert alarm2.schedule.days == ['mon', 'fri']


def test_alarm_settings_defaults():
    s = AlarmSettings()
    assert s.timezone == 'UTC'
    assert s.fallback.card_id is None


def test_alarm_config_from_yaml_dict():
    """AlarmConfig.model_validate() handles nested dicts from YAML"""
    raw = {
        'label': 'Test',
        'time': '06:00',
        'enabled': True,
        'schedule': {'type': 'weekly', 'days': ['mon'], 'end_date': None},
        'content': {'card_id': 'abc'},
        'volume': {'fade_in': False, 'start': 0, 'target': 70, 'restore_after': True},
        'max_duration': None,
        'catch_up_window': 0,
        'post_alarm': 'stop',
        'snooze_duration': None,
    }
    alarm = AlarmConfig.model_validate(raw)
    assert alarm.time == '06:00'
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test/alarmclock/test_models.py -v
```
Expected: FAIL with `ImportError`

**Step 3: Write the Pydantic models**

Create `src/jukebox/components/alarmclock/models.py`:

```python
"""Pydantic v2 models for alarm clock configuration.

These models provide type safety and validation for all alarm data.
YAML ↔ model round-trip is supported via model_dump() and model_validate().
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Day abbreviations
# ---------------------------------------------------------------------------

VALID_DAYS = frozenset(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
_TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


# ---------------------------------------------------------------------------
# Schedule models
# ---------------------------------------------------------------------------

class AlarmScheduleWeekly(BaseModel):
    """Recurring weekly alarm schedule."""

    type: Literal['weekly'] = 'weekly'
    days: list[str] = Field(default_factory=lambda: ['mon', 'tue', 'wed', 'thu', 'fri'])
    end_date: Optional[date] = None

    model_config = {'extra': 'ignore'}

    @field_validator('days', mode='before')
    @classmethod
    def validate_days(cls, v):
        if not isinstance(v, list):
            raise ValueError('days must be a list')
        invalid = [d for d in v if d not in VALID_DAYS]
        if invalid:
            raise ValueError(
                f"Invalid day abbreviations: {invalid}. "
                f"Must be one of: {sorted(VALID_DAYS)}"
            )
        return v


class AlarmScheduleOnce(BaseModel):
    """One-time alarm on a specific date."""

    type: Literal['once'] = 'once'
    date: date

    model_config = {'extra': 'ignore'}

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v


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

    card_id: Optional[str] = None

    model_config = {'extra': 'ignore'}


# ---------------------------------------------------------------------------
# Main alarm config
# ---------------------------------------------------------------------------

class AlarmConfig(BaseModel):
    """Complete configuration for a single alarm."""

    label: str = ''
    time: str = '07:00'
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

    @field_validator('time')
    @classmethod
    def validate_time(cls, v):
        if not _TIME_RE.match(v):
            raise ValueError(
                f"Invalid time format '{v}'. Must be HH:MM (24h), e.g. '07:30'"
            )
        return v


# ---------------------------------------------------------------------------
# Settings models
# ---------------------------------------------------------------------------

class AlarmFallback(BaseModel):
    """Global fallback audio configuration."""

    card_id: Optional[str] = None
    file: Optional[str] = None

    model_config = {'extra': 'ignore'}


class AlarmSettings(BaseModel):
    """Global alarm clock settings."""

    timezone: str = 'UTC'
    fallback: AlarmFallback = Field(default_factory=AlarmFallback)

    model_config = {'extra': 'ignore'}
```

**Step 4: Run tests**

```bash
python -m pytest test/alarmclock/test_models.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/jukebox/components/alarmclock/models.py \
        test/alarmclock/test_models.py
git commit -m "feat(alarmclock): add Pydantic v2 models for type-safe alarm configuration"
```

---

## Task 3: AlarmManager — CRUD with Pydantic validation

**Files:**
- Create: `src/jukebox/components/alarmclock/alarm_manager.py`
- Create: `test/alarmclock/test_alarm_manager.py`

**Step 1: Write the failing tests**

Create `test/alarmclock/test_alarm_manager.py`:

```python
import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import pytest
from pydantic import ValidationError
import jukebox.cfghandler as cfghandler
from components.alarmclock.alarm_manager import AlarmManager
from components.alarmclock.models import AlarmConfig, AlarmScheduleWeekly


def _fresh_cfg(name_suffix=''):
    """Create an isolated, empty config handler."""
    import uuid
    cfg = cfghandler.get_handler(f'ac_test_{uuid.uuid4().hex}')
    cfg.config_dict({'settings': {'timezone': 'UTC',
                                  'fallback': {'card_id': None, 'file': None}},
                     'alarms': {}})
    return cfg


def _make_manager():
    return AlarmManager(_fresh_cfg())


def _basic_alarm_dict():
    return {
        'label': 'Morning',
        'time': '07:00',
        'schedule': {'type': 'weekly', 'days': ['mon', 'tue'], 'end_date': None},
        'content': {'card_id': '9999'},
        'enabled': True,
    }


def test_add_returns_id():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    assert alarm_id.startswith('alarm_')


def test_add_validates_config():
    """Adding an alarm with an invalid time raises ValidationError"""
    mgr = _make_manager()
    with pytest.raises(ValidationError):
        mgr.add({'time': '99:00',
                 'schedule': {'type': 'weekly', 'days': ['mon']},
                 'content': {'card_id': '1'}})


def test_get_returns_alarm_config_model():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    alarm = mgr.get(alarm_id)
    assert isinstance(alarm, AlarmConfig)
    assert alarm.time == '07:00'


def test_get_nonexistent_returns_none():
    mgr = _make_manager()
    assert mgr.get('alarm_missing') is None


def test_list_returns_dict_of_configs():
    mgr = _make_manager()
    mgr.add(_basic_alarm_dict())
    mgr.add({**_basic_alarm_dict(), 'time': '08:00'})
    alarms = mgr.list()
    assert len(alarms) == 2
    for v in alarms.values():
        assert isinstance(v, AlarmConfig)


def test_update_patches_fields():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    mgr.update(alarm_id, {'label': 'Updated', 'time': '09:00'})
    alarm = mgr.get(alarm_id)
    assert alarm.label == 'Updated'
    assert alarm.time == '09:00'


def test_update_validates_patched_value():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    with pytest.raises(ValidationError):
        mgr.update(alarm_id, {'time': 'not-a-time'})


def test_update_nonexistent_raises_keyerror():
    mgr = _make_manager()
    with pytest.raises(KeyError):
        mgr.update('alarm_ghost', {'label': 'x'})


def test_delete_removes_alarm():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    mgr.delete(alarm_id)
    assert mgr.get(alarm_id) is None


def test_delete_nonexistent_raises_keyerror():
    mgr = _make_manager()
    with pytest.raises(KeyError):
        mgr.delete('alarm_ghost')


def test_set_enabled_toggles():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    mgr.set_enabled(alarm_id, False)
    assert mgr.get(alarm_id).enabled is False
    mgr.set_enabled(alarm_id, True)
    assert mgr.get(alarm_id).enabled is True


def test_add_defaults_applied():
    """Fields not provided get proper Pydantic defaults"""
    mgr = _make_manager()
    alarm_id = mgr.add({
        'time': '06:00',
        'schedule': {'type': 'weekly', 'days': ['fri']},
        'content': {'card_id': '42'},
    })
    alarm = mgr.get(alarm_id)
    assert alarm.enabled is True
    assert alarm.post_alarm == 'stop'
    assert alarm.volume.target == 70
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test/alarmclock/test_alarm_manager.py -v
```
Expected: FAIL with `ImportError`

**Step 3: Write AlarmManager**

Create `src/jukebox/components/alarmclock/alarm_manager.py`:

```python
"""AlarmManager: CRUD operations for alarm configurations.

All alarm data is validated through Pydantic models on read and write.
The underlying storage is a jukebox ConfigHandler (YAML-backed).
"""

import logging
import uuid
from typing import Dict, Optional

from .models import AlarmConfig

logger = logging.getLogger('jb.alarmclock.manager')


class AlarmManager:
    """Manages alarm CRUD operations against a ConfigHandler.

    The ConfigHandler must be loaded before AlarmManager is created.
    AlarmManager does NOT save to disk — callers must call cfg.save()
    after mutations that should persist.

    All public methods return or accept validated AlarmConfig instances
    or plain dicts that are validated through AlarmConfig on entry.
    """

    def __init__(self, cfg):
        """
        :param cfg: A loaded jukebox.cfghandler.ConfigHandler instance.
        """
        self._cfg = cfg

    def _new_id(self) -> str:
        """Generate a unique alarm ID that doesn't exist in current config."""
        existing = set(self._cfg.getn('alarms', default={}).keys())
        for _ in range(100):
            alarm_id = f"alarm_{uuid.uuid4().hex[:8]}"
            if alarm_id not in existing:
                return alarm_id
        raise RuntimeError("Failed to generate unique alarm ID after 100 tries")

    def add(self, alarm_data: dict) -> str:
        """Validate and add a new alarm. Returns the new alarm ID.

        :param alarm_data: Dict of alarm fields (validated by AlarmConfig)
        :raises pydantic.ValidationError: If alarm_data fails validation
        """
        validated = AlarmConfig.model_validate(alarm_data)
        alarm_id = self._new_id()
        with self._cfg:
            if 'alarms' not in self._cfg:
                self._cfg['alarms'] = {}
            self._cfg['alarms'][alarm_id] = validated.model_dump(mode='json')
        logger.info(f"Added alarm '{alarm_id}': '{validated.label}'")
        return alarm_id

    def get(self, alarm_id: str) -> Optional[AlarmConfig]:
        """Return validated AlarmConfig for alarm_id, or None if not found."""
        alarms = self._cfg.getn('alarms', default={})
        if alarm_id not in alarms:
            return None
        # Convert ruamel.yaml CommentedMap to plain dict for Pydantic
        raw = dict(alarms[alarm_id])
        return AlarmConfig.model_validate(raw)

    def list(self) -> Dict[str, AlarmConfig]:
        """Return dict of {alarm_id: AlarmConfig} for all alarms."""
        alarms = self._cfg.getn('alarms', default={})
        result = {}
        for alarm_id, raw in alarms.items():
            try:
                result[alarm_id] = AlarmConfig.model_validate(dict(raw))
            except Exception as e:
                logger.error(f"Failed to validate alarm '{alarm_id}': {e}")
        return result

    def update(self, alarm_id: str, diff: dict) -> None:
        """Patch fields on an existing alarm, re-validating the result.

        :raises KeyError: If alarm_id does not exist
        :raises pydantic.ValidationError: If the patched config fails validation
        """
        alarms = self._cfg.getn('alarms', default={})
        if alarm_id not in alarms:
            raise KeyError(f"Alarm not found: '{alarm_id}'")

        # Merge and re-validate
        merged = dict(alarms[alarm_id])
        merged.update(diff)
        validated = AlarmConfig.model_validate(merged)

        with self._cfg:
            self._cfg['alarms'][alarm_id] = validated.model_dump(mode='json')
        logger.debug(f"Updated alarm '{alarm_id}': {list(diff.keys())}")

    def delete(self, alarm_id: str) -> None:
        """Delete an alarm.

        :raises KeyError: If alarm_id does not exist
        """
        with self._cfg:
            alarms = self._cfg.getn('alarms', default={})
            if alarm_id not in alarms:
                raise KeyError(f"Alarm not found: '{alarm_id}'")
            del alarms[alarm_id]
        logger.info(f"Deleted alarm '{alarm_id}'")

    def set_enabled(self, alarm_id: str, enabled: bool) -> None:
        """Enable or disable an alarm without deleting it."""
        self.update(alarm_id, {'enabled': enabled})
```

**Step 4: Run tests**

```bash
python -m pytest test/alarmclock/test_alarm_manager.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/jukebox/components/alarmclock/alarm_manager.py \
        test/alarmclock/test_alarm_manager.py
git commit -m "feat(alarmclock): add type-safe AlarmManager with Pydantic validation"
```

---

## Task 4: Recurrence logic — `next_fire_time()`

**Files:**
- Create: `src/jukebox/components/alarmclock/scheduler.py`
- Create: `test/alarmclock/test_recurrence.py`

**Step 1: Write the failing tests**

Create `test/alarmclock/test_recurrence.py`:

```python
import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

from datetime import datetime
from zoneinfo import ZoneInfo
from components.alarmclock.models import AlarmConfig, AlarmScheduleWeekly, AlarmScheduleOnce
from components.alarmclock.scheduler import next_fire_time

UTC = ZoneInfo('UTC')
BERLIN = ZoneInfo('Europe/Berlin')


def _weekly(days, time='07:30', end_date=None, enabled=True):
    return AlarmConfig(
        time=time,
        schedule=AlarmScheduleWeekly(days=days, end_date=end_date),
        content={'card_id': '1'},
        enabled=enabled,
    )


def _once(date_str, time='07:00', enabled=True):
    return AlarmConfig(
        time=time,
        schedule=AlarmScheduleOnce(date=date_str),
        content={'card_id': '1'},
        enabled=enabled,
    )


def dt(year, month, day, hour, minute, tz=UTC):
    return datetime(year, month, day, hour, minute, tzinfo=tz)


# --- Weekly ---

def test_weekly_fires_later_today():
    """Monday alarm at 07:30, it's 06:00 Monday → fires today"""
    alarm = _weekly(['mon'])
    after = dt(2026, 3, 2, 6, 0)   # Monday 2026-03-02
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 2, 7, 30)


def test_weekly_wraps_to_next_week():
    """Monday alarm, already past time today → fires next Monday"""
    alarm = _weekly(['mon'])
    after = dt(2026, 3, 2, 8, 0)   # Monday, 08:00 - after alarm
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 9, 7, 30)  # Next Monday


def test_weekly_multiple_days_picks_nearest():
    """Mon+Wed alarm, Tuesday 06:00 → fires Wednesday"""
    alarm = _weekly(['mon', 'wed'], time='08:00')
    after = dt(2026, 3, 3, 6, 0)   # Tuesday
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 4, 8, 0)   # Wednesday


def test_weekly_end_date_past_returns_none():
    """Alarm past its end_date returns None"""
    alarm = _weekly(['mon'], end_date='2026-03-01')
    after = dt(2026, 3, 2, 6, 0)   # After end_date
    assert next_fire_time(alarm, after, UTC) is None


def test_weekly_all_days_fires_tomorrow():
    """Daily alarm, past today's time → fires tomorrow"""
    alarm = _weekly(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], time='09:00')
    after = dt(2026, 3, 2, 10, 0)  # Monday 10:00
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 3, 9, 0)   # Tuesday


def test_weekly_disabled_returns_none():
    alarm = _weekly(['mon'], enabled=False)
    after = dt(2026, 3, 2, 6, 0)
    assert next_fire_time(alarm, after, UTC) is None


# --- Once ---

def test_once_in_future_returns_datetime():
    alarm = _once('2030-06-15', time='07:00')
    after = dt(2026, 1, 1, 0, 0)
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2030, 6, 15, 7, 0)


def test_once_in_past_returns_none():
    alarm = _once('2020-01-01', time='07:00')
    after = dt(2026, 3, 1, 0, 0)
    assert next_fire_time(alarm, after, UTC) is None


def test_once_exact_same_second_returns_none():
    """Alarm at exact after_dt is not 'after' — returns None"""
    alarm = _once('2026-03-02', time='07:00')
    after = dt(2026, 3, 2, 7, 0)
    assert next_fire_time(alarm, after, UTC) is None


# --- DST ---

def test_dst_spring_forward_fires_at_wall_clock_time():
    """Alarm at 07:30 still fires at 07:30 on/after DST spring forward"""
    # Europe/Berlin: clocks spring forward 2026-03-29 02:00 → 03:00 (Sunday)
    alarm = _weekly(['sun'], time='07:30')
    after = dt(2026, 3, 29, 0, 0, tz=BERLIN)
    result = next_fire_time(alarm, after, BERLIN)

    assert result is not None
    assert result.hour == 7
    assert result.minute == 30
    # After spring forward, Berlin is CEST (UTC+2)
    import datetime as _dt
    assert result.utcoffset() == _dt.timedelta(hours=2)
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test/alarmclock/test_recurrence.py -v
```
Expected: FAIL with `ImportError`

**Step 3: Write `scheduler.py` with `next_fire_time()`**

Create `src/jukebox/components/alarmclock/scheduler.py`:

```python
"""Alarm scheduling: recurrence calculation and background scheduler thread."""

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple, Dict
from zoneinfo import ZoneInfo

from .models import AlarmConfig, AlarmScheduleWeekly, AlarmScheduleOnce

logger = logging.getLogger('jb.alarmclock.scheduler')

DAY_NAMES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


def _parse_time(time_str: str) -> Tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute)."""
    h, m = time_str.split(':')
    return int(h), int(m)


def next_fire_time(alarm: AlarmConfig, after_dt: datetime,
                   tz: ZoneInfo) -> Optional[datetime]:
    """Calculate the next datetime this alarm should fire, strictly after `after_dt`.

    :param alarm: Validated AlarmConfig instance
    :param after_dt: Timezone-aware (or naive) datetime; next fire time is strictly after this
    :param tz: ZoneInfo for wall-clock time interpretation
    :return: Next fire datetime (timezone-aware, in `tz`) or None
    """
    if not alarm.enabled:
        return None

    hour, minute = _parse_time(alarm.time)

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
        target_weekdays = {DAY_NAMES.index(d) for d in schedule.days}
        if not target_weekdays:
            return None

        for delta_days in range(0, 8):
            candidate = after_dt + timedelta(days=delta_days)
            # Build wall-clock datetime for this candidate day
            fire_dt = datetime(
                candidate.year, candidate.month, candidate.day,
                hour, minute, tzinfo=tz
            )

            if fire_dt <= after_dt:
                continue

            if fire_dt.weekday() not in target_weekdays:
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

    def __init__(self,
                 alarms_getter: Callable[[], Dict[str, AlarmConfig]],
                 on_fire: Callable[[str, AlarmConfig], None],
                 timezone: ZoneInfo):
        """
        :param alarms_getter: Zero-arg callable returning {alarm_id: AlarmConfig}
        :param on_fire: Called with (alarm_id, alarm_config) when alarm fires
        :param timezone: ZoneInfo for wall-clock time interpretation
        """
        self._alarms_getter = alarms_getter
        self._on_fire = on_fire
        self._tz = timezone
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

    def _find_next(self) -> Tuple[Optional[str], Optional[AlarmConfig], Optional[datetime]]:
        """Find the alarm with the earliest upcoming fire time."""
        now = datetime.now(self._tz)
        alarms = self._alarms_getter()
        next_id: Optional[str] = None
        next_cfg: Optional[AlarmConfig] = None
        next_dt: Optional[datetime] = None

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

            if fire_dt is None:
                logger.debug("No pending alarms — sleeping indefinitely")
                self._wakeup.wait()
                continue

            now = datetime.now(self._tz)
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
            now = datetime.now(self._tz)
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
```

**Step 4: Run all recurrence and scheduler tests**

```bash
python -m pytest test/alarmclock/test_recurrence.py -v
```
Expected: All PASS

**Step 5: Add scheduler thread tests**

Create `test/alarmclock/test_scheduler_thread.py`:

```python
import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import threading, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from components.alarmclock.models import AlarmConfig, AlarmScheduleOnce
from components.alarmclock.scheduler import AlarmScheduler

UTC = ZoneInfo('UTC')


def _one_shot_alarm(seconds_from_now=0.1, catch_up=5):
    fire_time = datetime.now(UTC) + timedelta(seconds=seconds_from_now)
    return {
        'alarm_001': AlarmConfig(
            time=fire_time.strftime('%H:%M'),
            schedule=AlarmScheduleOnce(date=fire_time.strftime('%Y-%m-%d')),
            content={'card_id': '1'},
            catch_up_window=catch_up,
        )
    }


def test_scheduler_fires_callback():
    fired = threading.Event()
    fired_ids = []

    def on_fire(alarm_id, alarm_cfg):
        fired_ids.append(alarm_id)
        fired.set()

    alarms = _one_shot_alarm(seconds_from_now=0.15)
    scheduler = AlarmScheduler(
        alarms_getter=lambda: alarms,
        on_fire=on_fire,
        timezone=UTC,
    )
    scheduler.start()
    assert fired.wait(timeout=2.0), "Alarm did not fire within 2 seconds"
    assert 'alarm_001' in fired_ids
    scheduler.stop()


def test_disabled_alarm_not_fired():
    fired = threading.Event()
    alarms = _one_shot_alarm(seconds_from_now=0.15)
    alarms['alarm_001'] = alarms['alarm_001'].model_copy(update={'enabled': False})

    scheduler = AlarmScheduler(
        alarms_getter=lambda: alarms,
        on_fire=lambda a, c: fired.set(),
        timezone=UTC,
    )
    scheduler.start()
    fired.wait(timeout=0.5)
    assert not fired.is_set()
    scheduler.stop()


def test_wakeup_does_not_block():
    scheduler = AlarmScheduler(
        alarms_getter=lambda: {},
        on_fire=lambda a, c: None,
        timezone=UTC,
    )
    scheduler.start()
    scheduler.wakeup()
    scheduler.wakeup()
    scheduler.stop()
```

**Step 6: Run scheduler thread tests**

```bash
python -m pytest test/alarmclock/test_scheduler_thread.py -v
```
Expected: All PASS

**Step 7: Commit**

```bash
git add src/jukebox/components/alarmclock/scheduler.py \
        test/alarmclock/test_recurrence.py \
        test/alarmclock/test_scheduler_thread.py
git commit -m "feat(alarmclock): add next_fire_time() and AlarmScheduler thread"
```

---

## Task 5: Volume fade-in

**Files:**
- Create: `src/jukebox/components/alarmclock/fade_in.py`
- Create: `test/alarmclock/test_fade_in.py`

**Step 1: Write the failing tests**

Create `test/alarmclock/test_fade_in.py`:

```python
import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import threading
from components.alarmclock.fade_in import FadeIn


def test_generates_correct_steps():
    calls = []
    FadeIn(start=10, target=70, ramp_seconds=0.05, steps=5,
           set_volume_fn=calls.append).run_sync()
    assert len(calls) == 5
    assert calls[0] == 10
    assert calls[-1] == 70
    assert all(calls[i] <= calls[i + 1] for i in range(len(calls) - 1))


def test_start_equals_target():
    calls = []
    FadeIn(start=50, target=50, ramp_seconds=0.01, steps=3,
           set_volume_fn=calls.append).run_sync()
    assert all(v == 50 for v in calls)


def test_clamps_to_valid_range():
    calls = []
    FadeIn(start=0, target=100, ramp_seconds=0.05, steps=5,
           set_volume_fn=calls.append).run_sync()
    assert all(0 <= v <= 100 for v in calls)


def test_cancel_stops_early():
    calls = []
    fade = FadeIn(start=0, target=100, ramp_seconds=0.5, steps=10,
                  set_volume_fn=calls.append)
    t = threading.Thread(target=fade.run_sync)
    t.start()
    import time; time.sleep(0.08)
    fade.cancel()
    t.join(timeout=2)
    assert len(calls) < 10
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test/alarmclock/test_fade_in.py -v
```

**Step 3: Write FadeIn**

Create `src/jukebox/components/alarmclock/fade_in.py`:

```python
"""Volume fade-in for alarm clock activation."""

import logging
import threading
from typing import Callable

logger = logging.getLogger('jb.alarmclock.fadein')


class FadeIn:
    """Ramps volume linearly from `start` to `target` over `ramp_seconds` in `steps` steps.

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
        self._thread: threading.Thread = None

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
```

**Step 4: Run tests**

```bash
python -m pytest test/alarmclock/test_fade_in.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/jukebox/components/alarmclock/fade_in.py \
        test/alarmclock/test_fade_in.py
git commit -m "feat(alarmclock): add FadeIn volume ramp"
```

---

## Task 6: AlarmExecutor — fire/snooze/dismiss state machine

**Files:**
- Create: `src/jukebox/components/alarmclock/executor.py`
- Create: `test/alarmclock/test_executor.py`

**Step 1: Write the failing tests**

Create `test/alarmclock/test_executor.py`:

```python
import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

from unittest.mock import MagicMock
from components.alarmclock.executor import AlarmExecutor
from components.alarmclock.models import AlarmConfig, AlarmScheduleWeekly, AlarmVolumeConfig


def _alarm(fade_in=False, start=30, target=70, restore_after=True,
           post_alarm='stop', snooze_duration=600, max_duration=None):
    return AlarmConfig(
        label='Test',
        time='07:00',
        schedule=AlarmScheduleWeekly(days=['mon']),
        content={'card_id': '1234'},
        volume=AlarmVolumeConfig(fade_in=fade_in, start=start, target=target,
                                  restore_after=restore_after),
        post_alarm=post_alarm,
        snooze_duration=snooze_duration,
        max_duration=max_duration,
    )


def _make_executor(alarm_cfg=None, card_found=True):
    cfg = alarm_cfg or _alarm()
    get_volume = MagicMock(return_value=50)
    set_volume = MagicMock()
    stop_player = MagicMock()
    trigger_card = MagicMock(return_value=card_found)
    trigger_fallback = MagicMock()
    publish = MagicMock()

    ex = AlarmExecutor(
        alarm_id='alarm_001',
        alarm_cfg=cfg,
        get_volume_fn=get_volume,
        set_volume_fn=set_volume,
        stop_player_fn=stop_player,
        trigger_card_fn=trigger_card,
        trigger_fallback_fn=trigger_fallback,
        publish_fn=publish,
    )
    mocks = dict(get_volume=get_volume, set_volume=set_volume,
                 stop_player=stop_player, trigger_card=trigger_card,
                 trigger_fallback=trigger_fallback, publish=publish)
    return ex, mocks


def test_initial_state_is_idle():
    ex, _ = _make_executor()
    assert ex.state == 'idle'


def test_fire_saves_pre_alarm_volume():
    ex, mocks = _make_executor()
    ex.fire()
    assert ex.pre_alarm_volume == 50


def test_fire_stops_player():
    ex, mocks = _make_executor()
    ex.fire()
    mocks['stop_player'].assert_called_once()


def test_fire_triggers_card():
    ex, mocks = _make_executor()
    ex.fire()
    mocks['trigger_card'].assert_called_once_with('1234')


def test_fire_uses_fallback_when_card_not_found():
    ex, mocks = _make_executor(card_found=False)
    ex.fire()
    mocks['trigger_fallback'].assert_called_once()


def test_fire_sets_start_volume():
    ex, mocks = _make_executor(_alarm(fade_in=False, start=40))
    ex.fire()
    mocks['set_volume'].assert_called_with(40)


def test_fire_sets_state_firing():
    ex, mocks = _make_executor()
    ex.fire()
    assert ex.state == 'firing'


def test_fire_publishes_firing_state():
    ex, mocks = _make_executor()
    ex.fire()
    states = [c[0][1].get('state') for c in mocks['publish'].call_args_list
              if isinstance(c[0][1], dict)]
    assert 'firing' in states


def test_dismiss_restores_volume():
    ex, mocks = _make_executor(_alarm(restore_after=True))
    ex.fire()
    ex.dismiss()
    set_calls = [c[0][0] for c in mocks['set_volume'].call_args_list]
    assert 50 in set_calls  # pre-alarm volume restored


def test_dismiss_skips_restore_when_configured():
    ex, mocks = _make_executor(_alarm(restore_after=False))
    ex.fire()
    mocks['set_volume'].reset_mock()
    ex.dismiss()
    mocks['set_volume'].assert_not_called()


def test_dismiss_sets_idle_state():
    ex, mocks = _make_executor()
    ex.fire()
    ex.dismiss()
    assert ex.state == 'idle'


def test_snooze_returns_duration():
    ex, mocks = _make_executor(_alarm(snooze_duration=600))
    ex.fire()
    assert ex.snooze() == 600


def test_snooze_sets_snoozed_state():
    ex, mocks = _make_executor()
    ex.fire()
    ex.snooze()
    assert ex.state == 'snoozed'
```

**Step 2: Run to verify they fail**

```bash
python -m pytest test/alarmclock/test_executor.py -v
```

**Step 3: Write AlarmExecutor**

Create `src/jukebox/components/alarmclock/executor.py`:

```python
"""AlarmExecutor: state machine for a single firing alarm instance."""

import logging
import threading
from typing import Callable, Optional

from .fade_in import FadeIn
from .models import AlarmConfig

logger = logging.getLogger('jb.alarmclock.executor')


class AlarmExecutor:
    """Manages the fire → active → snoozed/idle lifecycle of a single alarm.

    All side effects are injected as callables for testability.
    """

    def __init__(self,
                 alarm_id: str,
                 alarm_cfg: AlarmConfig,
                 get_volume_fn: Callable[[], int],
                 set_volume_fn: Callable[[int], None],
                 stop_player_fn: Callable[[], None],
                 trigger_card_fn: Callable[[str], bool],
                 trigger_fallback_fn: Callable[[], None],
                 publish_fn: Callable[[str, dict], None]):
        """
        :param trigger_card_fn: Called with card_id. Returns True if card was found.
        :param trigger_fallback_fn: Called when card not found or content unavailable.
        :param publish_fn: Called with (alarm_id, state_dict) on state transitions.
        """
        self._alarm_id = alarm_id
        self._cfg = alarm_cfg
        self._get_volume = get_volume_fn
        self._set_volume = set_volume_fn
        self._stop_player = stop_player_fn
        self._trigger_card = trigger_card_fn
        self._trigger_fallback = trigger_fallback_fn
        self._publish = publish_fn

        self.state: str = 'idle'
        self.pre_alarm_volume: Optional[int] = None
        self._fade_in: Optional[FadeIn] = None
        self._max_timer: Optional[threading.Timer] = None

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

        self.state = 'firing'
        self._publish_state()

    def dismiss(self):
        """Dismiss alarm and restore pre-alarm state."""
        logger.info(f"Dismissing alarm '{self._alarm_id}'")
        self._cancel_timers()

        if self._cfg.volume.restore_after and self.pre_alarm_volume is not None:
            self._set_volume(self.pre_alarm_volume)

        # post_alarm == 'resume': The caller (AlarmController) is responsible for
        # resuming playback if needed, as it requires player state captured before fire().

        self.state = 'idle'
        self.pre_alarm_volume = None
        self._publish_state()

    def snooze(self) -> int:
        """Snooze alarm. Returns snooze duration in seconds."""
        duration = self._cfg.snooze_duration or 600
        logger.info(f"Snoozing alarm '{self._alarm_id}' for {duration}s")
        self._cancel_timers()
        self.state = 'snoozed'
        self._publish_state()
        return duration

    def _cancel_timers(self):
        if self._fade_in and self._fade_in.is_alive():
            self._fade_in.cancel()
        if self._max_timer is not None:
            self._max_timer.cancel()
            self._max_timer = None

    def _publish_state(self):
        self._publish(self._alarm_id, {
            'alarm_id': self._alarm_id,
            'state': self.state if self.state != 'idle' else None,
            'label': self._cfg.label,
        })
```

**Step 4: Run tests**

```bash
python -m pytest test/alarmclock/test_executor.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/jukebox/components/alarmclock/executor.py \
        test/alarmclock/test_executor.py
git commit -m "feat(alarmclock): add AlarmExecutor state machine"
```

---

## Task 7: Full plugin wiring — RPC, PubSub, RFID callback

**Files:**
- Modify: `src/jukebox/components/alarmclock/__init__.py`

**Step 1: Replace scaffold with full implementation**

Replace the contents of `src/jukebox/components/alarmclock/__init__.py` with:

```python
# RPi-Jukebox-RFID Version 3
# Copyright (c) See file LICENSE in project root folder
"""Alarm Clock Plugin

Schedules RFID card actions at specific times. Configuration validated
via Pydantic v2 models. Stored in shared/settings/alarmclock.yaml.

## RPC endpoints (package name from jukebox.yaml, default: alarmclock)

  alarmclock.list()                   → dict[str, dict] of all alarms
  alarmclock.get(alarm_id)            → dict or None
  alarmclock.add(alarm_config)        → new alarm_id: str
  alarmclock.update(alarm_id, diff)   → None
  alarmclock.delete(alarm_id)         → None
  alarmclock.set_enabled(alarm_id, enabled) → None
  alarmclock.snooze()                 → None
  alarmclock.dismiss()                → None
  alarmclock.get_next_fire_time()     → ISO str or None
  alarmclock.get_active()             → dict or None

## PubSub topics

  alarmclock.alarms             → serialized alarm list (on change)
  alarmclock.active             → {alarm_id, state, label} or {state: null}
  alarmclock.next_fire_time     → ISO datetime string or null
"""

import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import jukebox.cfghandler
import jukebox.plugs as plugs
import jukebox.publishing as publishing
import jukebox.utils as utils

from .alarm_manager import AlarmManager
from .scheduler import AlarmScheduler, next_fire_time
from .executor import AlarmExecutor
from .models import AlarmConfig

logger = logging.getLogger('jb.alarmclock')

cfg = jukebox.cfghandler.get_handler('alarmclock')
cfg_main = jukebox.cfghandler.get_handler('jukebox')
cfg_cards = jukebox.cfghandler.get_handler('cards')

_manager: AlarmManager = None
_scheduler: AlarmScheduler = None
_active_executor: AlarmExecutor = None
_snooze_timer: threading.Timer = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_timezone() -> ZoneInfo:
    tz_name = cfg.getn('settings', 'timezone', default='UTC')
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"Invalid timezone '{tz_name}', falling back to UTC")
        return ZoneInfo('UTC')


def _get_volume() -> int:
    result = plugs.call_ignore_errors('volume', 'ctrl', 'get_volume')
    return result if isinstance(result, int) else 0


def _set_volume(vol: int):
    plugs.call_ignore_errors('volume', 'ctrl', 'set_volume', args=[vol])


def _stop_player():
    plugs.call_ignore_errors('player', 'ctrl', 'stop')


def _trigger_card(card_id: str) -> bool:
    """Execute the card's RPC command. Returns True if card was found."""
    card_cmd = cfg_cards.getn(card_id, default=None)
    if card_cmd is None:
        return False
    utils.decode_and_call_rpc_command(card_cmd, logger)
    return True


def _trigger_fallback():
    """Play global fallback audio."""
    fallback_card = cfg.getn('settings', 'fallback', 'card_id', default=None)
    fallback_file = cfg.getn('settings', 'fallback', 'file', default=None)
    if fallback_card:
        _trigger_card(fallback_card)
    elif fallback_file:
        plugs.call_ignore_errors('player', 'ctrl', 'play_single', args=[fallback_file])
    else:
        logger.warning("Alarm fired but no content and no global fallback configured")


def _publish_active(alarm_id=None, state=None, label=''):
    publishing.get_publisher().send(
        f'{plugs.loaded_as(__name__)}.active',
        {'alarm_id': alarm_id, 'state': state, 'label': label}
    )


def _publish_alarms():
    # Serialize AlarmConfig objects to JSON-compatible dicts for PubSub
    alarms_raw = {k: v.model_dump(mode='json')
                  for k, v in _manager.list().items()}
    publishing.get_publisher().send(
        f'{plugs.loaded_as(__name__)}.alarms',
        alarms_raw
    )


def _publish_next_fire_time():
    nft = get_next_fire_time()
    publishing.get_publisher().send(
        f'{plugs.loaded_as(__name__)}.next_fire_time',
        nft
    )


def _on_alarm_fire(alarm_id: str, alarm_cfg: AlarmConfig):
    """Callback from AlarmScheduler when an alarm fires."""
    global _active_executor

    with _lock:
        if _active_executor is not None and _active_executor.state != 'idle':
            logger.warning(
                f"Alarm '{alarm_id}' fired but another alarm is already active — skipping"
            )
            return

        executor = AlarmExecutor(
            alarm_id=alarm_id,
            alarm_cfg=alarm_cfg,
            get_volume_fn=_get_volume,
            set_volume_fn=_set_volume,
            stop_player_fn=_stop_player,
            trigger_card_fn=_trigger_card,
            trigger_fallback_fn=_trigger_fallback,
            publish_fn=lambda aid, data: _publish_active(
                alarm_id=data.get('alarm_id'),
                state=data.get('state'),
                label=data.get('label', ''),
            ),
        )
        _active_executor = executor

    executor.fire()
    _publish_next_fire_time()


def _on_rfid_card_detected(card_id: str, state):
    """RFID callback: scan the alarm's own card to dismiss."""
    with _lock:
        executor = _active_executor
    if executor is None or executor.state == 'idle':
        return
    alarm_card = executor._cfg.content.card_id
    if card_id == alarm_card:
        logger.info(f"RFID '{card_id}' matched active alarm — dismissing")
        dismiss()


# ---------------------------------------------------------------------------
# RPC endpoints
# ---------------------------------------------------------------------------

@plugs.register
def list() -> dict:
    """Return all alarms as JSON-serializable dicts."""
    return {k: v.model_dump(mode='json') for k, v in _manager.list().items()}


@plugs.register
def get(alarm_id: str) -> dict:
    """Return alarm config dict or None."""
    alarm = _manager.get(alarm_id)
    return alarm.model_dump(mode='json') if alarm else None


@plugs.register
def add(alarm_config: dict) -> str:
    """Create a new alarm. Returns the new alarm ID."""
    alarm_id = _manager.add(alarm_config)
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()
    return alarm_id


@plugs.register
def update(alarm_id: str, diff: dict) -> None:
    """Patch fields on an existing alarm."""
    _manager.update(alarm_id, diff)
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()


@plugs.register
def delete(alarm_id: str) -> None:
    """Delete an alarm."""
    _manager.delete(alarm_id)
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()


@plugs.register
def set_enabled(alarm_id: str, enabled: bool) -> None:
    """Enable or disable an alarm."""
    _manager.set_enabled(alarm_id, enabled)
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()


@plugs.register
def snooze() -> None:
    """Snooze the currently active alarm."""
    global _active_executor, _snooze_timer
    with _lock:
        executor = _active_executor
    if executor is None or executor.state != 'firing':
        logger.warning("snooze() called but no alarm is firing")
        return

    snooze_duration = executor.snooze()

    def _resnooze():
        _on_alarm_fire(executor._alarm_id, executor._cfg)

    with _lock:
        if _snooze_timer is not None:
            _snooze_timer.cancel()
        _snooze_timer = threading.Timer(snooze_duration, _resnooze)
        _snooze_timer.daemon = True
        _snooze_timer.start()


@plugs.register
def dismiss() -> None:
    """Dismiss the currently active alarm."""
    global _active_executor, _snooze_timer
    with _lock:
        executor = _active_executor
        if _snooze_timer is not None:
            _snooze_timer.cancel()
            _snooze_timer = None

    if executor is None or executor.state == 'idle':
        logger.warning("dismiss() called but no alarm is active")
        return

    executor.dismiss()
    with _lock:
        _active_executor = None
    _publish_next_fire_time()


@plugs.register
def get_next_fire_time() -> str:
    """Return ISO datetime string of next alarm, or None."""
    tz = _get_timezone()
    now = datetime.now(tz)
    earliest = None
    for alarm_cfg in _manager.list().values():
        nft = next_fire_time(alarm_cfg, now, tz)
        if nft is not None and (earliest is None or nft < earliest):
            earliest = nft
    return earliest.isoformat() if earliest else None


@plugs.register
def get_active() -> dict:
    """Return info about the currently active alarm, or None."""
    with _lock:
        executor = _active_executor
    if executor is None or executor.state == 'idle':
        return None
    return {
        'alarm_id': executor._alarm_id,
        'state': executor.state,
        'label': executor._cfg.label,
    }


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------

@plugs.finalize
def finalize():
    global _manager, _scheduler

    config_file = cfg_main.setndefault(
        'alarmclock', 'config_file',
        value='../../shared/settings/alarmclock.yaml'
    )
    try:
        cfg.load(config_file)
    except FileNotFoundError:
        cfg.config_dict({'settings': {'timezone': 'UTC',
                                      'fallback': {'card_id': None, 'file': None}},
                         'alarms': {}})
        logger.warning(f"Alarm config not found, created empty: '{config_file}'")
        cfg.save(only_if_changed=False)

    cfg.setndefault('settings', 'timezone', value='UTC')
    cfg.setndefault('settings', 'fallback', 'card_id', value=None)
    cfg.setndefault('settings', 'fallback', 'file', value=None)

    _manager = AlarmManager(cfg)

    tz = _get_timezone()
    _scheduler = AlarmScheduler(
        alarms_getter=_manager.list,
        on_fire=_on_alarm_fire,
        timezone=tz,
    )
    _scheduler.start()

    # Register RFID card detect callback for alarm dismiss
    try:
        rfid_callbacks = plugs.get('rfid', 'reader', 'rfid_card_detect_callbacks')
        if rfid_callbacks is not None:
            rfid_callbacks.register(_on_rfid_card_detected)
    except Exception:
        logger.debug("Could not register RFID callback (rfid plugin may not be loaded)")

    _publish_alarms()
    _publish_next_fire_time()
    logger.info(f"Alarm clock initialized — timezone: '{tz}'")


@plugs.atexit
def atexit(**ignored_kwargs):
    global _scheduler, _active_executor
    if _scheduler:
        _scheduler.stop()
    if _active_executor and _active_executor.state != 'idle':
        _active_executor.dismiss()
    cfg.save(only_if_changed=True)
    return [_scheduler._thread] if _scheduler else []
```

**Step 2: Run all backend tests**

```bash
python -m pytest test/alarmclock/ -v
```
Expected: All PASS

**Step 3: Lint**

```bash
cd src/jukebox && python -m flake8 components/alarmclock/ --max-line-length=120
```
Fix any issues.

**Step 4: Commit**

```bash
git add src/jukebox/components/alarmclock/__init__.py
git commit -m "feat(alarmclock): wire full plugin with RPC endpoints, PubSub, and RFID dismiss callback"
```

---

## Task 8: Frontend — RPC commands

**Files:**
- Modify: `src/webapp/src/commands/index.js`

**Step 1: Add alarm clock commands**

In `src/webapp/src/commands/index.js`, inside the `commands` object before the final `}`, add:

```javascript
  // Alarm Clock
  alarmsList: {
    _package: 'alarmclock',
    plugin: 'list',
  },
  alarmsAdd: {
    _package: 'alarmclock',
    plugin: 'add',
    argKeys: ['alarm_config'],
  },
  alarmsUpdate: {
    _package: 'alarmclock',
    plugin: 'update',
    argKeys: ['alarm_id', 'diff'],
  },
  alarmsDelete: {
    _package: 'alarmclock',
    plugin: 'delete',
    argKeys: ['alarm_id'],
  },
  alarmsSetEnabled: {
    _package: 'alarmclock',
    plugin: 'set_enabled',
    argKeys: ['alarm_id', 'enabled'],
  },
  alarmsSnooze: {
    _package: 'alarmclock',
    plugin: 'snooze',
  },
  alarmsDismiss: {
    _package: 'alarmclock',
    plugin: 'dismiss',
  },
  alarmsGetActive: {
    _package: 'alarmclock',
    plugin: 'get_active',
  },
  alarmsGetNextFireTime: {
    _package: 'alarmclock',
    plugin: 'get_next_fire_time',
  },
```

**Step 2: Verify webapp builds**

```bash
cd src/webapp && npm run build 2>&1 | tail -5
```

**Step 3: Commit**

```bash
git add src/webapp/src/commands/index.js
git commit -m "feat(alarmclock): add frontend RPC command definitions"
```

---

## Task 9: Frontend — i18n translation strings

**Files:**
- Modify: `src/webapp/public/locales/en/translation.json`
- Modify: `src/webapp/public/locales/de/translation.json`

**Step 1: Add English strings**

In `src/webapp/public/locales/en/translation.json`, inside `"settings": { ... }`, add `"alarms"` key:

```json
"alarms": {
  "title": "Alarms",
  "no-alarms": "No alarms configured.",
  "add": "Add Alarm",
  "edit": "Edit",
  "delete": "Delete",
  "enabled": "Enabled",
  "next-fire": "Next: {{datetime}}",
  "never": "Never",
  "dialog": {
    "title-add": "New Alarm",
    "title-edit": "Edit Alarm",
    "save": "Save",
    "cancel": "Cancel",
    "label": "Name (optional)",
    "time": "Time",
    "schedule": "Schedule",
    "days": "Days",
    "presets": {
      "daily": "Daily",
      "weekdays": "Weekdays",
      "weekends": "Weekends",
      "custom": "Custom"
    },
    "end-date": "End Date (optional)",
    "once-date": "Date",
    "content": "Content",
    "content-card-id": "Card ID",
    "content-scan": "Scan Card",
    "content-scanning": "Scanning...",
    "volume": "Volume",
    "fade-in": "Fade In",
    "start-volume": "Start Volume",
    "target-volume": "Target Volume",
    "max-duration": "Max Duration",
    "max-duration-off": "No limit",
    "snooze": "Snooze Duration",
    "snooze-off": "No snooze",
    "post-alarm": "After alarm",
    "post-alarm-stop": "Stop playback",
    "post-alarm-resume": "Resume playback",
    "catch-up": "Catch-up window (seconds)"
  },
  "active": {
    "title": "Alarm ringing",
    "dismiss": "Dismiss",
    "snooze": "Snooze"
  },
  "days-short": {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun"
  }
}
```

**Step 2: Add German strings**

In `src/webapp/public/locales/de/translation.json`, inside `"settings"`, add:

```json
"alarms": {
  "title": "Wecker",
  "no-alarms": "Keine Wecker konfiguriert.",
  "add": "Wecker hinzufügen",
  "edit": "Bearbeiten",
  "delete": "Löschen",
  "enabled": "Aktiviert",
  "next-fire": "Nächster: {{datetime}}",
  "never": "Nie",
  "dialog": {
    "title-add": "Neuer Wecker",
    "title-edit": "Wecker bearbeiten",
    "save": "Speichern",
    "cancel": "Abbrechen",
    "label": "Name (optional)",
    "time": "Uhrzeit",
    "schedule": "Zeitplan",
    "days": "Wochentage",
    "presets": {
      "daily": "Täglich",
      "weekdays": "Werktags",
      "weekends": "Wochenende",
      "custom": "Benutzerdefiniert"
    },
    "end-date": "Enddatum (optional)",
    "once-date": "Datum",
    "content": "Inhalt",
    "content-card-id": "Karten-ID",
    "content-scan": "Karte scannen",
    "content-scanning": "Scanne...",
    "volume": "Lautstärke",
    "fade-in": "Einblenden",
    "start-volume": "Startlautstärke",
    "target-volume": "Ziellautstärke",
    "max-duration": "Maximale Dauer",
    "max-duration-off": "Kein Limit",
    "snooze": "Schlummerdauer",
    "snooze-off": "Kein Schlummer",
    "post-alarm": "Nach dem Wecker",
    "post-alarm-stop": "Wiedergabe stoppen",
    "post-alarm-resume": "Wiedergabe fortsetzen",
    "catch-up": "Nachholzeit (Sekunden)"
  },
  "active": {
    "title": "Wecker klingelt",
    "dismiss": "Ausschalten",
    "snooze": "Schlummern"
  },
  "days-short": {
    "mon": "Mo",
    "tue": "Di",
    "wed": "Mi",
    "thu": "Do",
    "fri": "Fr",
    "sat": "Sa",
    "sun": "So"
  }
}
```

**Step 3: Commit**

```bash
git add src/webapp/public/locales/en/translation.json \
        src/webapp/public/locales/de/translation.json
git commit -m "feat(alarmclock): add i18n strings (en + de)"
```

---

## Task 10: Frontend — alarm list component

**Files:**
- Create: `src/webapp/src/components/Settings/alarms/index.js`

**Step 1: Create directory and component**

```bash
mkdir -p src/webapp/src/components/Settings/alarms
```

Create `src/webapp/src/components/Settings/alarms/index.js`:

```javascript
import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Switch,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import request from '../../../utils/request';
import AlarmDialog from './alarm-dialog';

const SettingsAlarms = () => {
  const { t } = useTranslation();
  const [alarms, setAlarms] = useState({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAlarm, setEditingAlarm] = useState(null);

  const fetchAlarms = useCallback(async () => {
    const { result } = await request('alarmclock.list');
    if (result) setAlarms(result);
  }, []);

  useEffect(() => { fetchAlarms(); }, [fetchAlarms]);

  const handleToggle = async (alarm_id, current) => {
    await request('alarmclock.set_enabled', { alarm_id, enabled: !current });
    fetchAlarms();
  };

  const handleDelete = async (alarm_id) => {
    await request('alarmclock.delete', { alarm_id });
    fetchAlarms();
  };

  const handleSave = async (alarm_config) => {
    if (editingAlarm) {
      await request('alarmclock.update', { alarm_id: editingAlarm.id, diff: alarm_config });
    } else {
      await request('alarmclock.add', { alarm_config });
    }
    setDialogOpen(false);
    fetchAlarms();
  };

  return (
    <Card>
      <CardHeader title={t('settings.alarms.title')} />
      <Divider />
      <CardContent>
        {Object.keys(alarms).length === 0 && (
          <Typography variant="body2" color="text.secondary">
            {t('settings.alarms.no-alarms')}
          </Typography>
        )}
        <List disablePadding>
          {Object.entries(alarms).map(([alarm_id, cfg]) => (
            <ListItem
              key={alarm_id}
              disableGutters
              divider
              secondaryAction={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Switch
                    size="small"
                    checked={cfg.enabled ?? true}
                    onChange={() => handleToggle(alarm_id, cfg.enabled)}
                  />
                  <IconButton size="small"
                    onClick={() => { setEditingAlarm({ id: alarm_id, config: cfg }); setDialogOpen(true); }}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" onClick={() => handleDelete(alarm_id)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Box>
              }
            >
              <ListItemText
                primary={cfg.label || cfg.time}
                secondary={`${cfg.time} · ${cfg.schedule?.days?.join(', ') || cfg.schedule?.date || ''}`}
              />
            </ListItem>
          ))}
        </List>
        <Box sx={{ mt: 2 }}>
          <Button variant="outlined"
            onClick={() => { setEditingAlarm(null); setDialogOpen(true); }}>
            {t('settings.alarms.add')}
          </Button>
        </Box>
      </CardContent>
      <AlarmDialog
        open={dialogOpen}
        initialConfig={editingAlarm?.config ?? null}
        onSave={handleSave}
        onClose={() => setDialogOpen(false)}
      />
    </Card>
  );
};

export default SettingsAlarms;
```

**Step 2: Commit**

```bash
git add src/webapp/src/components/Settings/alarms/index.js
git commit -m "feat(alarmclock): add alarm list component"
```

---

## Task 11: Frontend — alarm editor dialog

**Files:**
- Create: `src/webapp/src/components/Settings/alarms/alarm-dialog.js`

**Step 1: Create the dialog**

Create `src/webapp/src/components/Settings/alarms/alarm-dialog.js`:

```javascript
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  FormGroup,
  FormLabel,
  MenuItem,
  Select,
  Slider,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';

const ALL_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const PRESETS = {
  daily: ALL_DAYS,
  weekdays: ['mon', 'tue', 'wed', 'thu', 'fri'],
  weekends: ['sat', 'sun'],
};

const DEFAULT_CONFIG = {
  label: '', time: '07:00', enabled: true,
  schedule: { type: 'weekly', days: ['mon', 'tue', 'wed', 'thu', 'fri'], end_date: null },
  content: { card_id: '' },
  volume: { fade_in: false, start: 0, target: 70, restore_after: true },
  max_duration: null, catch_up_window: 300, post_alarm: 'stop', snooze_duration: 600,
};

const AlarmDialog = ({ open, initialConfig, onSave, onClose }) => {
  const { t } = useTranslation();
  const [cfg, setCfg] = useState(DEFAULT_CONFIG);

  useEffect(() => {
    if (open) setCfg(initialConfig ? { ...DEFAULT_CONFIG, ...initialConfig } : DEFAULT_CONFIG);
  }, [open, initialConfig]);

  const patch = (path, value) => {
    setCfg(prev => {
      const next = { ...prev };
      const keys = path.split('.');
      let obj = next;
      for (let i = 0; i < keys.length - 1; i++) {
        obj[keys[i]] = { ...obj[keys[i]] };
        obj = obj[keys[i]];
      }
      obj[keys[keys.length - 1]] = value;
      return next;
    });
  };

  const schedType = cfg.schedule?.type ?? 'weekly';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {initialConfig ? t('settings.alarms.dialog.title-edit') : t('settings.alarms.dialog.title-add')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>

        <TextField label={t('settings.alarms.dialog.label')} size="small" fullWidth
          value={cfg.label} onChange={e => patch('label', e.target.value)} />

        <TextField label={t('settings.alarms.dialog.time')} type="time" size="small"
          value={cfg.time} onChange={e => patch('time', e.target.value)}
          inputProps={{ step: 60 }} />

        <div>
          <FormLabel>{t('settings.alarms.dialog.schedule')}</FormLabel>
          <ToggleButtonGroup value={schedType} exclusive size="small" sx={{ mt: 0.5 }}
            onChange={(_, v) => v && patch('schedule.type', v)}>
            <ToggleButton value="weekly">Weekly</ToggleButton>
            <ToggleButton value="once">Once</ToggleButton>
          </ToggleButtonGroup>
        </div>

        {schedType === 'weekly' && <>
          <div>
            <FormLabel>{t('settings.alarms.dialog.days')}</FormLabel>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
              {Object.keys(PRESETS).map(p => (
                <Button key={p} size="small" variant="outlined"
                  onClick={() => patch('schedule.days', PRESETS[p])}>
                  {t(`settings.alarms.dialog.presets.${p}`)}
                </Button>
              ))}
            </div>
            <FormGroup row sx={{ mt: 1 }}>
              {ALL_DAYS.map(day => (
                <FormControlLabel key={day}
                  control={<Checkbox size="small"
                    checked={(cfg.schedule?.days ?? []).includes(day)}
                    onChange={() => {
                      const days = cfg.schedule?.days ?? [];
                      patch('schedule.days', days.includes(day)
                        ? days.filter(d => d !== day)
                        : [...days, day]);
                    }} />}
                  label={t(`settings.alarms.days-short.${day}`)} />
              ))}
            </FormGroup>
          </div>
          <TextField label={t('settings.alarms.dialog.end-date')} type="date" size="small"
            InputLabelProps={{ shrink: true }}
            value={cfg.schedule?.end_date ?? ''}
            onChange={e => patch('schedule.end_date', e.target.value || null)} />
        </>}

        {schedType === 'once' && (
          <TextField label={t('settings.alarms.dialog.once-date')} type="date" size="small"
            InputLabelProps={{ shrink: true }}
            value={cfg.schedule?.date ?? ''}
            onChange={e => patch('schedule.date', e.target.value)} />
        )}

        <TextField label={t('settings.alarms.dialog.content-card-id')} size="small" fullWidth
          value={cfg.content?.card_id ?? ''}
          onChange={e => patch('content.card_id', e.target.value)}
          helperText="RFID card ID (leave empty to use fallback)" />

        <FormControlLabel
          control={<Switch checked={cfg.volume?.fade_in ?? false}
            onChange={e => patch('volume.fade_in', e.target.checked)} />}
          label={t('settings.alarms.dialog.fade-in')} />

        <div>
          <Typography variant="caption">
            {t('settings.alarms.dialog.start-volume')}: {cfg.volume?.start ?? 0}%
          </Typography>
          <Slider value={cfg.volume?.start ?? 0} min={0} max={100} step={5}
            onChange={(_, v) => patch('volume.start', v)} />
        </div>

        <div>
          <Typography variant="caption">
            {t('settings.alarms.dialog.target-volume')}: {cfg.volume?.target ?? 70}%
          </Typography>
          <Slider value={cfg.volume?.target ?? 70} min={0} max={100} step={5}
            onChange={(_, v) => patch('volume.target', v)} />
        </div>

        <Select size="small" value={cfg.max_duration ?? 0}
          onChange={e => patch('max_duration', e.target.value || null)}>
          <MenuItem value={0}>{t('settings.alarms.dialog.max-duration-off')}</MenuItem>
          <MenuItem value={1800}>30 min</MenuItem>
          <MenuItem value={3600}>60 min</MenuItem>
          <MenuItem value={5400}>90 min</MenuItem>
          <MenuItem value={7200}>120 min</MenuItem>
        </Select>

        <Select size="small" value={cfg.snooze_duration ?? 0}
          onChange={e => patch('snooze_duration', e.target.value || null)}>
          <MenuItem value={0}>{t('settings.alarms.dialog.snooze-off')}</MenuItem>
          <MenuItem value={300}>5 min</MenuItem>
          <MenuItem value={600}>10 min</MenuItem>
          <MenuItem value={900}>15 min</MenuItem>
        </Select>

        <Select size="small" value={cfg.post_alarm ?? 'stop'}
          onChange={e => patch('post_alarm', e.target.value)}>
          <MenuItem value="stop">{t('settings.alarms.dialog.post-alarm-stop')}</MenuItem>
          <MenuItem value="resume">{t('settings.alarms.dialog.post-alarm-resume')}</MenuItem>
        </Select>

      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('settings.alarms.dialog.cancel')}</Button>
        <Button onClick={() => onSave(cfg)} variant="contained">
          {t('settings.alarms.dialog.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AlarmDialog;
```

**Step 2: Commit**

```bash
git add src/webapp/src/components/Settings/alarms/alarm-dialog.js
git commit -m "feat(alarmclock): add alarm editor dialog"
```

---

## Task 12: Frontend — active alarm banner and Settings integration

**Files:**
- Create: `src/webapp/src/components/Settings/alarms/active-alarm-banner.js`
- Modify: `src/webapp/src/components/Settings/index.js`

**Step 1: Create the active alarm banner**

Create `src/webapp/src/components/Settings/alarms/active-alarm-banner.js`:

```javascript
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Stack } from '@mui/material';
import request from '../../../utils/request';

const ActiveAlarmBanner = () => {
  const { t } = useTranslation();
  const [activeAlarm, setActiveAlarm] = useState(null);

  useEffect(() => {
    // Poll every 5 seconds.
    // Future improvement: subscribe to alarmclock.active PubSub topic instead.
    const check = async () => {
      const { result } = await request('alarmclock.get_active');
      setActiveAlarm(result ?? null);
    };
    check();
    const interval = setInterval(check, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!activeAlarm) return null;

  const handleDismiss = async () => {
    await request('alarmclock.dismiss');
    setActiveAlarm(null);
  };

  const handleSnooze = async () => {
    await request('alarmclock.snooze');
    setActiveAlarm(null);
  };

  return (
    <Alert
      severity="info"
      sx={{ mb: 1 }}
      action={
        <Stack direction="row" spacing={1}>
          {activeAlarm.state !== 'snoozed' && (
            <Button size="small" color="inherit" onClick={handleSnooze}>
              {t('settings.alarms.active.snooze')}
            </Button>
          )}
          <Button size="small" color="inherit" onClick={handleDismiss}>
            {t('settings.alarms.active.dismiss')}
          </Button>
        </Stack>
      }
    >
      {t('settings.alarms.active.title')}: {activeAlarm.label || activeAlarm.alarm_id}
    </Alert>
  );
};

export default ActiveAlarmBanner;
```

**Step 2: Integrate into Settings page**

In `src/webapp/src/components/Settings/index.js`:

Add at the top with the other imports:
```javascript
import SettingsAlarms from './alarms/index';
import ActiveAlarmBanner from './alarms/active-alarm-banner';
```

Add to the JSX grid, as the first two `<Grid item>` blocks (before `<SettingsStatus />`):
```javascript
      <Grid item>
        <ActiveAlarmBanner />
      </Grid>
      <Grid item>
        <SettingsAlarms />
      </Grid>
```

**Step 3: Build webapp**

```bash
cd src/webapp && npm run build 2>&1 | tail -10
```
Expected: Build succeeds with no new errors.

**Step 4: Commit**

```bash
git add src/webapp/src/components/Settings/alarms/active-alarm-banner.js \
        src/webapp/src/components/Settings/index.js
git commit -m "feat(alarmclock): add active alarm banner and integrate Alarms into Settings"
```

---

## Task 13: Final verification

**Step 1: Run full backend test suite**

```bash
cd /home/brainslush/gitprojects/RPi-Jukebox-RFID
python -m pytest test/alarmclock/ -v --tb=short
```
Expected: All PASS. Fix any failures before proceeding.

**Step 2: Lint**

```bash
cd src/jukebox && python -m flake8 components/alarmclock/ --max-line-length=120
```

**Step 3: Confirm webapp builds**

```bash
cd src/webapp && npm run build 2>&1 | grep -c "error"
```
Expected: 0

**Step 4: Manual smoke test (on running jukebox)**

1. Open web UI → Settings → Alarms
2. Click "Add Alarm", set time 1–2 minutes from now, select a weekday, assign a known card ID
3. Save and wait for alarm to fire
4. Verify playback starts and active alarm banner appears
5. Click Dismiss → verify playback stops and banner disappears
6. Add a recurring weekly alarm, verify next fire time is shown
7. Disable the alarm with the toggle → verify it no longer fires

**Step 5: Save memory note and final commit**

```bash
git add .
git commit -m "feat(alarmclock): complete alarm clock implementation

Pydantic v2 models for type-safe alarm configuration, custom power-
efficient scheduler using threading.Event.wait(), full CRUD via RPC,
fade-in volume, snooze/dismiss via web UI and RFID card, DST-safe
scheduling with zoneinfo, catch-up window for missed alarms.

Backend: alarmclock plugin with models, manager, scheduler, executor
Frontend: alarm list, editor dialog, active alarm banner (en+de i18n)"
```

---

## Notes for implementors

- **`plugs.loaded_as(__name__)`**: Returns the RPC package name (e.g. `alarmclock` as set in jukebox.yaml). All PubSub topics must use this for the prefix.
- **RFID callback**: `plugs.get('rfid', 'reader', 'rfid_card_detect_callbacks')` — check if this is the correct API. See `src/jukebox/components/rfid/reader/__init__.py`.
- **Volume API**: Verify the exact method path for `get_volume`/`set_volume` in `src/jukebox/components/volume/__init__.py`. The call path may be `'volume', 'ctrl', 'get_volume'` or similar.
- **`post_alarm: resume`**: The executor marks this as a comment; the full resume requires capturing `plugs.call('player', 'ctrl', 'playerstatus')` before fire and restoring it after dismiss. Defer to a follow-up if needed.
- **Active alarm banner polling**: Replace with PubSub subscription using the existing `PubSubContext` pattern when desired for production quality.
- **Pydantic `model_dump(mode='json')`**: Always use `mode='json'` when serializing for YAML/RPC to ensure dates serialize as ISO strings, not `date` objects.
