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
      const { result } = await request('alarmsGetActive');
      setActiveAlarm(result ?? null);
    };
    check();
    const interval = setInterval(check, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!activeAlarm) return null;

  const handleDismiss = async () => {
    await request('alarmsDismiss');
    setActiveAlarm(null);
  };

  const handleSnooze = async () => {
    await request('alarmsSnooze');
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
