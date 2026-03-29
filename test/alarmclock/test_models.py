import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import pytest
from datetime import date, time
from pathlib import Path
from pydantic import ValidationError
from components.alarmclock.models import (
    AlarmConfig,
    AlarmScheduleWeekly,
    AlarmScheduleOnce,
    AlarmVolumeConfig,
    AlarmSettings,
    AlarmFallback,
)

# Weekday index constants for readability
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


# --- Schedule models ---

def test_weekly_schedule_valid():
    s = AlarmScheduleWeekly(days=(True, False, True, False, True, False, False))
    assert s.days[MON] is True
    assert s.days[WED] is True
    assert s.days[FRI] is True
    assert s.days[TUE] is False
    assert s.end_date is None


def test_weekly_schedule_default_is_mon_fri():
    s = AlarmScheduleWeekly()
    assert all(s.days[i] for i in range(5))   # Mon–Fri True
    assert not any(s.days[i] for i in (5, 6))  # Sat–Sun False


def test_weekly_schedule_end_date_from_string():
    s = AlarmScheduleWeekly(days=(True, False, False, False, False, False, False),
                             end_date='2030-06-01')
    assert s.end_date == date(2030, 6, 1)


def test_weekly_schedule_end_date_from_date_object():
    s = AlarmScheduleWeekly(days=(True, False, False, False, False, False, False),
                             end_date=date(2030, 6, 1))
    assert s.end_date == date(2030, 6, 1)


def test_once_schedule_from_string():
    s = AlarmScheduleOnce(date='2030-01-15')
    assert s.date == date(2030, 1, 15)


def test_once_schedule_from_date_object():
    s = AlarmScheduleOnce(date=date(2030, 1, 15))
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


def test_volume_config_out_of_range():
    with pytest.raises(ValidationError):
        AlarmVolumeConfig(start=150)


# --- AlarmConfig ---

def test_alarm_config_defaults():
    alarm = AlarmConfig()
    assert alarm.enabled is True
    assert alarm.time == time(7, 0)
    assert alarm.post_alarm == 'stop'


def test_alarm_config_time_from_string():
    alarm = AlarmConfig(time='07:30')
    assert alarm.time == time(7, 30)


def test_alarm_config_time_from_time_object():
    alarm = AlarmConfig(time=time(8, 0))
    assert alarm.time == time(8, 0)


def test_alarm_config_weekly():
    alarm = AlarmConfig(
        time='07:30',
        schedule=AlarmScheduleWeekly(days=(True, True, False, False, False, False, False)),
        content={'card_id': '1234'},
    )
    assert alarm.enabled is True
    assert alarm.schedule.days[MON] is True
    assert alarm.schedule.days[TUE] is True
    assert alarm.schedule.days[WED] is False


def test_alarm_config_once():
    alarm = AlarmConfig(
        time='08:00',
        schedule=AlarmScheduleOnce(date='2030-01-01'),
        content={'card_id': '5678'},
    )
    assert alarm.schedule.date.year == 2030


def test_alarm_config_invalid_time():
    with pytest.raises(ValidationError):
        AlarmConfig(time='25:00')


def test_alarm_config_invalid_post_alarm():
    with pytest.raises(ValidationError):
        AlarmConfig(post_alarm='invalid_value')


def test_alarm_config_roundtrip():
    """model_dump() → model_validate() preserves all fields"""
    alarm = AlarmConfig(
        label='Morning',
        time='07:00',
        schedule=AlarmScheduleWeekly(
            days=(True, False, False, False, True, False, False),
            end_date='2030-12-31'
        ),
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
    assert alarm2.schedule.days[MON] is True
    assert alarm2.schedule.days[FRI] is True


def test_alarm_settings_defaults():
    s = AlarmSettings()
    assert s.fallback.card_id is None


def test_alarm_fallback_file_is_path():
    f = AlarmFallback(file='/some/audio.mp3')
    assert isinstance(f.file, Path)


def test_alarm_config_from_yaml_dict():
    """AlarmConfig.model_validate() handles nested dicts from YAML"""
    raw = {
        'label': 'Test',
        'time': '06:00',
        'enabled': True,
        'schedule': {'type': 'weekly',
                     'days': (True, False, False, False, False, False, False),
                     'end_date': None},
        'content': {'card_id': 'abc'},
        'volume': {'fade_in': False, 'start': 0, 'target': 70, 'restore_after': True},
        'max_duration': None,
        'catch_up_window': 0,
        'post_alarm': 'stop',
        'snooze_duration': None,
    }
    alarm = AlarmConfig.model_validate(raw)
    assert alarm.time == time(6, 0)
