import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

from datetime import datetime, time
from zoneinfo import ZoneInfo
from components.alarmclock.models import AlarmConfig, AlarmScheduleWeekly, AlarmScheduleOnce
from components.alarmclock.scheduler import next_fire_time

UTC = ZoneInfo('UTC')
BERLIN = ZoneInfo('Europe/Berlin')

# Weekday index constants: Mon=0 ... Sun=6
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def _mask(*active_days: int) -> tuple:
    """Build a 7-bool WeekdayMask from active weekday indices."""
    return tuple(i in active_days for i in range(7))


def _weekly(days_indices, alarm_time='07:30', end_date=None, enabled=True):
    return AlarmConfig(
        time=alarm_time,
        schedule=AlarmScheduleWeekly(days=_mask(*days_indices), end_date=end_date),
        content={'card_id': '1'},
        enabled=enabled,
    )


def _once(date_str, alarm_time='07:00', enabled=True):
    return AlarmConfig(
        time=alarm_time,
        schedule=AlarmScheduleOnce(date=date_str),
        content={'card_id': '1'},
        enabled=enabled,
    )


def dt(year, month, day, hour, minute, tz=UTC):
    return datetime(year, month, day, hour, minute, tzinfo=tz)


# --- Weekly ---

def test_weekly_fires_later_today():
    """Monday alarm at 07:30, it's 06:00 Monday → fires today"""
    alarm = _weekly([MON])
    after = dt(2026, 3, 2, 6, 0)   # Monday 2026-03-02
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 2, 7, 30)


def test_weekly_wraps_to_next_week():
    """Monday alarm, already past time today → fires next Monday"""
    alarm = _weekly([MON])
    after = dt(2026, 3, 2, 8, 0)   # Monday, 08:00 - after alarm
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 9, 7, 30)  # Next Monday


def test_weekly_multiple_days_picks_nearest():
    """Mon+Wed alarm, Tuesday 06:00 → fires Wednesday"""
    alarm = _weekly([MON, WED], alarm_time='08:00')
    after = dt(2026, 3, 3, 6, 0)   # Tuesday
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 4, 8, 0)   # Wednesday


def test_weekly_end_date_past_returns_none():
    """Alarm past its end_date returns None"""
    alarm = _weekly([MON], end_date='2026-03-01')
    after = dt(2026, 3, 2, 6, 0)   # After end_date
    assert next_fire_time(alarm, after, UTC) is None


def test_weekly_all_days_fires_tomorrow():
    """Daily alarm, past today's time → fires tomorrow"""
    alarm = _weekly([MON, TUE, WED, THU, FRI, SAT, SUN], alarm_time='09:00')
    after = dt(2026, 3, 2, 10, 0)  # Monday 10:00
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2026, 3, 3, 9, 0)   # Tuesday


def test_weekly_disabled_returns_none():
    alarm = _weekly([MON], enabled=False)
    after = dt(2026, 3, 2, 6, 0)
    assert next_fire_time(alarm, after, UTC) is None


# --- Once ---

def test_once_in_future_returns_datetime():
    alarm = _once('2030-06-15', alarm_time='07:00')
    after = dt(2026, 1, 1, 0, 0)
    result = next_fire_time(alarm, after, UTC)
    assert result == dt(2030, 6, 15, 7, 0)


def test_once_in_past_returns_none():
    alarm = _once('2020-01-01', alarm_time='07:00')
    after = dt(2026, 3, 1, 0, 0)
    assert next_fire_time(alarm, after, UTC) is None


def test_once_exact_same_second_returns_none():
    """Alarm at exact after_dt is not 'after' — returns None"""
    alarm = _once('2026-03-02', alarm_time='07:00')
    after = dt(2026, 3, 2, 7, 0)
    assert next_fire_time(alarm, after, UTC) is None


# --- DST ---

def test_dst_spring_forward_fires_at_wall_clock_time():
    """Alarm at 07:30 still fires at 07:30 on/after DST spring forward"""
    # Europe/Berlin: clocks spring forward 2026-03-29 02:00 → 03:00 (Sunday)
    alarm = _weekly([SUN], alarm_time='07:30')
    after = dt(2026, 3, 29, 0, 0, tz=BERLIN)
    result = next_fire_time(alarm, after, BERLIN)

    assert result is not None
    assert result.hour == 7
    assert result.minute == 30
    # After spring forward, Berlin is CEST (UTC+2)
    import datetime as _dt
    assert result.utcoffset() == _dt.timedelta(hours=2)
