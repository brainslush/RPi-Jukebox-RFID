import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from components.alarmclock.models import AlarmConfig, AlarmId, AlarmScheduleOnce
from components.alarmclock.scheduler import AlarmScheduler

UTC = ZoneInfo('UTC')

# Fixed alarm fire time used in all tests
_ALARM_DT = datetime(2030, 6, 15, 7, 0, tzinfo=UTC)
_ALARM_DATE = _ALARM_DT.date()
_ALARM_TIME = _ALARM_DT.time()


def _one_shot_alarms() -> dict[AlarmId, AlarmConfig]:
    return {
        AlarmId('alarm_001'): AlarmConfig(
            time=_ALARM_TIME,
            schedule=AlarmScheduleOnce(date=_ALARM_DATE),
            content={'card_id': '1'},
            catch_up_window=60,
        )
    }


def _scheduler_with_mock_clock(alarms_getter, on_fire, seconds_before_alarm=0.1):
    """Create a scheduler whose clock starts just before _ALARM_DT."""
    start = _ALARM_DT - timedelta(seconds=seconds_before_alarm)
    epoch = [start]

    def mock_now():
        # Advance time a little each call so the scheduler eventually sees the alarm fire
        epoch[0] = epoch[0] + timedelta(milliseconds=50)
        return epoch[0]

    return AlarmScheduler(
        alarms_getter=alarms_getter,
        on_fire=on_fire,
        timezone=UTC,
        _now_fn=mock_now,
    )


def test_scheduler_fires_callback():
    fired = threading.Event()
    fired_ids = []

    def on_fire(alarm_id, alarm_cfg):
        fired_ids.append(alarm_id)
        fired.set()

    scheduler = _scheduler_with_mock_clock(
        alarms_getter=_one_shot_alarms,
        on_fire=on_fire,
    )
    scheduler.start()
    assert fired.wait(timeout=5.0), "Alarm did not fire within 5 seconds"
    assert AlarmId('alarm_001') in fired_ids
    scheduler.stop()


def test_disabled_alarm_not_fired():
    fired = threading.Event()

    def disabled_alarms():
        alarms = _one_shot_alarms()
        alarms[AlarmId('alarm_001')] = alarms[AlarmId('alarm_001')].model_copy(
            update={'enabled': False}
        )
        return alarms

    scheduler = _scheduler_with_mock_clock(
        alarms_getter=disabled_alarms,
        on_fire=lambda a, c: fired.set(),
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
