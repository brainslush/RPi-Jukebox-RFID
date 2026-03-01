import React from 'react';

import { Grid } from '@mui/material';

import SettingsAudio from './audio/index';
import SettingsAutoHotspot from './autohotspot';
import SettingsGeneral from './general';
import SettingsSecondSwipe from './secondswipe';
import SettingsStatus from './status/index';
import SettingsTimers from './timers/index';
import SystemControls from './systemcontrols';
import ActiveAlarmBanner from './alarms/active-alarm-banner';
import SettingsAlarms from './alarms/index';

import { useTheme } from '@mui/material/styles';

const Settings = () => {
  const theme = useTheme();
  const spacer = { marginBottom: theme.spacing(1) }

  return (
    <Grid
      container
      direction="column"
      id="settings"
      sx={{
        '& > .MuiGrid-item': spacer,
        padding: '10px',
      }}
    >
      <Grid item>
        <ActiveAlarmBanner />
      </Grid>
      <Grid item>
        <SettingsAlarms />
      </Grid>
      <Grid item>
        <SettingsStatus />
      </Grid>
      <Grid item>
        <SettingsGeneral />
      </Grid>
      <Grid item>
        <SettingsTimers />
      </Grid>
      <Grid item>
        <SettingsAudio />
      </Grid>
      <Grid item>
        <SystemControls />
      </Grid>
      <Grid item>
        <SettingsSecondSwipe />
      </Grid>
      <Grid item>
        <SettingsAutoHotspot />
      </Grid>
    </Grid>
  );
};

export default Settings;
