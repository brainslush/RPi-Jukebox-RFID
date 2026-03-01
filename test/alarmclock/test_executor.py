import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

from unittest.mock import MagicMock
from components.alarmclock.executor import AlarmExecutor
from components.alarmclock.models import AlarmActiveState, AlarmConfig, AlarmId, AlarmScheduleWeekly, AlarmVolumeConfig


def _alarm(fade_in=False, start=30, target=70, restore_after=True,
           post_alarm='stop', snooze_duration=600, max_duration=None):
    return AlarmConfig(
        label='Test',
        time='07:00',
        schedule=AlarmScheduleWeekly(days=(True, False, False, False, False, False, False)),
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
        alarm_id=AlarmId('alarm_001'),
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
    published = [c[0][0] for c in mocks['publish'].call_args_list
                 if isinstance(c[0][0], AlarmActiveState)]
    assert any(s.state == 'firing' for s in published)


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
