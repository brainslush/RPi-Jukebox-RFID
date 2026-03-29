# RPi-Jukebox-RFID Version 3
# Copyright (c) See file LICENSE in project root folder
"""Alarm Clock Plugin

Schedules RFID card actions at specific times. Configuration validated
via Pydantic v2 models. Stored in shared/settings/alarmclock.yaml.

## RPC endpoints (package name from jukebox.yaml, default: alarmclock)

  alarmclock.list()                         → dict[str, dict] of all alarms
  alarmclock.get(alarm_id)                  → dict or None
  alarmclock.add(alarm_config)              → new alarm_id: str
  alarmclock.update(alarm_id, diff)         → None
  alarmclock.delete(alarm_id)               → None
  alarmclock.set_enabled(alarm_id, enabled) → None
  alarmclock.snooze()                       → None
  alarmclock.dismiss()                      → None
  alarmclock.get_next_fire_time()           → ISO str or None
  alarmclock.get_active()                   → dict or None

## PubSub topics

  alarmclock.alarms             → serialized alarm list (on change)
  alarmclock.active             → AlarmActiveState dict or {state: null}
  alarmclock.next_fire_time     → ISO datetime string or null
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import jukebox.cfghandler
import jukebox.plugs as plugs
import jukebox.publishing as publishing
import jukebox.utils as utils

from .alarm_manager import AlarmManager
from .executor import AlarmExecutor
from .models import AlarmActiveState, AlarmConfig, AlarmId, CardId
from .scheduler import AlarmScheduler, next_fire_time

logger = logging.getLogger('jb.alarmclock')

cfg = jukebox.cfghandler.get_handler('alarmclock')
cfg_main = jukebox.cfghandler.get_handler('jukebox')
cfg_cards = jukebox.cfghandler.get_handler('cards')

_manager: AlarmManager | None = None
_scheduler: AlarmScheduler | None = None
_active_executor: AlarmExecutor | None = None
_snooze_timer: threading.Timer | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_timezone() -> ZoneInfo:
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, 'key'):
            return ZoneInfo(local_tz.key)
    except Exception:
        pass
    return ZoneInfo('UTC')


def _get_volume() -> int:
    result = plugs.call_ignore_errors('volume', 'ctrl', 'get_volume')
    return result if isinstance(result, int) else 0


def _set_volume(vol: int):
    plugs.call_ignore_errors('volume', 'ctrl', 'set_volume', args=[vol])


def _stop_player():
    plugs.call_ignore_errors('player', 'ctrl', 'stop')


def _trigger_card(card_id: CardId) -> bool:
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
        _trigger_card(CardId(fallback_card))
    elif fallback_file:
        plugs.call_ignore_errors('player', 'ctrl', 'play_single', args=[fallback_file])
    else:
        logger.warning("Alarm fired but no content and no global fallback configured")


def _publish_active(active_state: AlarmActiveState):
    publishing.get_publisher().send(
        f'{plugs.loaded_as(__name__)}.active',
        active_state.model_dump(mode='json')
    )


def _publish_alarms():
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


def _on_alarm_fire(alarm_id: AlarmId, alarm_cfg: AlarmConfig):
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
            publish_fn=_publish_active,
        )
        _active_executor = executor

    executor.fire()
    _publish_next_fire_time()


def _on_rfid_card_detected(card_id: str, state):
    """RFID callback: scanning the alarm's own card dismisses it."""
    with _lock:
        executor = _active_executor
    if executor is None or executor.state == 'idle':
        return
    alarm_card = executor._cfg.content.card_id
    if alarm_card and card_id == alarm_card:
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
def get(alarm_id: str) -> dict | None:
    """Return alarm config dict or None."""
    alarm = _manager.get(AlarmId(alarm_id))
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
    _manager.update(AlarmId(alarm_id), diff)
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()


@plugs.register
def delete(alarm_id: str) -> None:
    """Delete an alarm."""
    _manager.delete(AlarmId(alarm_id))
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()


@plugs.register
def set_enabled(alarm_id: str, enabled: bool) -> None:
    """Enable or disable an alarm."""
    _manager.set_enabled(AlarmId(alarm_id), enabled)
    cfg.save()
    _scheduler.wakeup()
    _publish_alarms()
    _publish_next_fire_time()


@plugs.register
def snooze() -> None:
    """Snooze the currently active alarm."""
    global _snooze_timer
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
def get_next_fire_time() -> str | None:
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
def get_active() -> dict | None:
    """Return AlarmActiveState dict for the active alarm, or None."""
    with _lock:
        executor = _active_executor
    if executor is None or executor.state == 'idle':
        return None
    return executor._active_state.model_dump(mode='json')


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
        cfg.config_dict({'settings': {'fallback': {'card_id': None, 'file': None}},
                         'alarms': {}})
        logger.warning(f"Alarm config not found, created empty: '{config_file}'")
        cfg.save(only_if_changed=False)

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
