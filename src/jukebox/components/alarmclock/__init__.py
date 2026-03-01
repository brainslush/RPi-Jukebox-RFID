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
