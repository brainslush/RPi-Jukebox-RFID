import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import pytest
from pydantic import ValidationError
import jukebox.cfghandler as cfghandler
from components.alarmclock.alarm_manager import AlarmManager
from components.alarmclock.models import AlarmConfig, AlarmScheduleWeekly


def _fresh_cfg():
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
        'schedule': {'type': 'weekly',
                     'days': (True, True, False, False, False, False, False),
                     'end_date': None},
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
                 'schedule': {'type': 'weekly',
                              'days': (True, False, False, False, False, False, False)},
                 'content': {'card_id': '1'}})


def test_get_returns_alarm_config_model():
    mgr = _make_manager()
    alarm_id = mgr.add(_basic_alarm_dict())
    alarm = mgr.get(alarm_id)
    assert isinstance(alarm, AlarmConfig)
    from datetime import time
    assert alarm.time == time(7, 0)


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
    from datetime import time
    assert alarm.time == time(9, 0)


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
        'schedule': {'type': 'weekly',
                     'days': (False, False, False, False, True, False, False)},
        'content': {'card_id': '42'},
    })
    alarm = mgr.get(alarm_id)
    assert alarm.enabled is True
    assert alarm.post_alarm == 'stop'
    assert alarm.volume.target == 70
