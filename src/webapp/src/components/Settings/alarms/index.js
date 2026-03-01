import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Switch,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import request from '../../../utils/request';
import AlarmDialog from './alarm-dialog';

const SettingsAlarms = () => {
  const { t } = useTranslation();
  const [alarms, setAlarms] = useState({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAlarm, setEditingAlarm] = useState(null);

  const fetchAlarms = useCallback(async () => {
    const { result } = await request('alarmsList');
    if (result) setAlarms(result);
  }, []);

  useEffect(() => { fetchAlarms(); }, [fetchAlarms]);

  const handleToggle = async (alarm_id, current) => {
    await request('alarmsSetEnabled', { alarm_id, enabled: !current });
    fetchAlarms();
  };

  const handleDelete = async (alarm_id) => {
    await request('alarmsDelete', { alarm_id });
    fetchAlarms();
  };

  const handleSave = async (alarm_config) => {
    if (editingAlarm) {
      await request('alarmsUpdate', { alarm_id: editingAlarm.id, diff: alarm_config });
    } else {
      await request('alarmsAdd', { alarm_config });
    }
    setDialogOpen(false);
    fetchAlarms();
  };

  return (
    <Card>
      <CardHeader title={t('settings.alarms.title')} />
      <Divider />
      <CardContent>
        {Object.keys(alarms).length === 0 && (
          <Typography variant="body2" color="text.secondary">
            {t('settings.alarms.no-alarms')}
          </Typography>
        )}
        <List disablePadding>
          {Object.entries(alarms).map(([alarm_id, cfg]) => (
            <ListItem
              key={alarm_id}
              disableGutters
              divider
              secondaryAction={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Switch
                    size="small"
                    checked={cfg.enabled ?? true}
                    onChange={() => handleToggle(alarm_id, cfg.enabled)}
                  />
                  <IconButton size="small"
                    onClick={() => { setEditingAlarm({ id: alarm_id, config: cfg }); setDialogOpen(true); }}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" onClick={() => handleDelete(alarm_id)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Box>
              }
            >
              <ListItemText
                primary={cfg.label || cfg.time}
                secondary={`${cfg.time} · ${cfg.schedule?.days?.join(', ') || cfg.schedule?.date || ''}`}
              />
            </ListItem>
          ))}
        </List>
        <Box sx={{ mt: 2 }}>
          <Button variant="outlined"
            onClick={() => { setEditingAlarm(null); setDialogOpen(true); }}>
            {t('settings.alarms.add')}
          </Button>
        </Box>
      </CardContent>
      <AlarmDialog
        open={dialogOpen}
        initialConfig={editingAlarm?.config ?? null}
        onSave={handleSave}
        onClose={() => setDialogOpen(false)}
      />
    </Card>
  );
};

export default SettingsAlarms;
