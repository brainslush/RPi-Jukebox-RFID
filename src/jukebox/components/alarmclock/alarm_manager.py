"""AlarmManager: CRUD operations for alarm configurations.

All alarm data is validated through Pydantic models on read and write.
The underlying storage is a jukebox ConfigHandler (YAML-backed).
"""

from __future__ import annotations

import logging
import uuid

from .models import AlarmConfig, AlarmId

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

    def _new_id(self) -> AlarmId:
        """Generate a unique alarm ID that doesn't exist in current config."""
        existing = set(self._cfg.getn('alarms', default={}).keys())
        for _ in range(100):
            alarm_id = AlarmId(f"alarm_{uuid.uuid4().hex[:8]}")
            if alarm_id not in existing:
                return alarm_id
        raise RuntimeError("Failed to generate unique alarm ID after 100 tries")

    def add(self, alarm_data: dict) -> AlarmId:
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

    def get(self, alarm_id: AlarmId) -> AlarmConfig | None:
        """Return validated AlarmConfig for alarm_id, or None if not found."""
        alarms = self._cfg.getn('alarms', default={})
        if alarm_id not in alarms:
            return None
        raw = dict(alarms[alarm_id])
        return AlarmConfig.model_validate(raw)

    def list(self) -> dict[AlarmId, AlarmConfig]:
        """Return dict of {alarm_id: AlarmConfig} for all alarms."""
        alarms = self._cfg.getn('alarms', default={})
        result: dict[AlarmId, AlarmConfig] = {}
        for alarm_id, raw in alarms.items():
            try:
                result[AlarmId(alarm_id)] = AlarmConfig.model_validate(dict(raw))
            except Exception as e:
                logger.error(f"Failed to validate alarm '{alarm_id}': {e}")
        return result

    def update(self, alarm_id: AlarmId, diff: dict) -> None:
        """Patch fields on an existing alarm, re-validating the result.

        :raises KeyError: If alarm_id does not exist
        :raises pydantic.ValidationError: If the patched config fails validation
        """
        alarms = self._cfg.getn('alarms', default={})
        if alarm_id not in alarms:
            raise KeyError(f"Alarm not found: '{alarm_id}'")

        merged = dict(alarms[alarm_id])
        merged.update(diff)
        validated = AlarmConfig.model_validate(merged)

        with self._cfg:
            self._cfg['alarms'][alarm_id] = validated.model_dump(mode='json')
        logger.debug(f"Updated alarm '{alarm_id}': {list(diff.keys())}")

    def delete(self, alarm_id: AlarmId) -> None:
        """Delete an alarm.

        :raises KeyError: If alarm_id does not exist
        """
        with self._cfg:
            alarms = self._cfg.getn('alarms', default={})
            if alarm_id not in alarms:
                raise KeyError(f"Alarm not found: '{alarm_id}'")
            del alarms[alarm_id]
        logger.info(f"Deleted alarm '{alarm_id}'")

    def set_enabled(self, alarm_id: AlarmId, enabled: bool) -> None:
        """Enable or disable an alarm without deleting it."""
        self.update(alarm_id, {'enabled': enabled})
