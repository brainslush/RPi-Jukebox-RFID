import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  FormGroup,
  FormLabel,
  MenuItem,
  Select,
  Slider,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';

// Weekday order: Mon=0 … Sun=6 — matches backend WeekdayMask tuple
const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

// Preset day masks as 7-bool arrays
const PRESETS = {
  daily:    [true,  true,  true,  true,  true,  true,  true],
  weekdays: [true,  true,  true,  true,  true,  false, false],
  weekends: [false, false, false, false, false, true,  true],
};

const DEFAULT_CONFIG = {
  label: '',
  time: '07:00',
  enabled: true,
  schedule: { type: 'weekly', days: PRESETS.weekdays, end_date: null },
  content: { card_id: '' },
  volume: { fade_in: false, start: 0, target: 70, restore_after: true },
  max_duration: null,
  catch_up_window: 300,
  post_alarm: 'stop',
  snooze_duration: 600,
};

const AlarmDialog = ({ open, initialConfig, onSave, onClose }) => {
  const { t } = useTranslation();
  const [cfg, setCfg] = useState(DEFAULT_CONFIG);

  useEffect(() => {
    if (open) setCfg(initialConfig ? { ...DEFAULT_CONFIG, ...initialConfig } : DEFAULT_CONFIG);
  }, [open, initialConfig]);

  const patch = (path, value) => {
    setCfg(prev => {
      const next = { ...prev };
      const keys = path.split('.');
      let obj = next;
      for (let i = 0; i < keys.length - 1; i++) {
        obj[keys[i]] = { ...obj[keys[i]] };
        obj = obj[keys[i]];
      }
      obj[keys[keys.length - 1]] = value;
      return next;
    });
  };

  const schedType = cfg.schedule?.type ?? 'weekly';
  // Normalize days — backend sends a 7-element array (from tuple serialization)
  const days = Array.isArray(cfg.schedule?.days)
    ? cfg.schedule.days
    : PRESETS.weekdays;

  const toggleDay = (idx) => {
    const next = [...days];
    next[idx] = !next[idx];
    patch('schedule.days', next);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {initialConfig ? t('settings.alarms.dialog.title-edit') : t('settings.alarms.dialog.title-add')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>

        <TextField label={t('settings.alarms.dialog.label')} size="small" fullWidth
          value={cfg.label} onChange={e => patch('label', e.target.value)} />

        <TextField label={t('settings.alarms.dialog.time')} type="time" size="small"
          value={cfg.time} onChange={e => patch('time', e.target.value)}
          inputProps={{ step: 60 }} />

        <div>
          <FormLabel>{t('settings.alarms.dialog.schedule')}</FormLabel>
          <ToggleButtonGroup value={schedType} exclusive size="small" sx={{ mt: 0.5 }}
            onChange={(_, v) => v && patch('schedule.type', v)}>
            <ToggleButton value="weekly">Weekly</ToggleButton>
            <ToggleButton value="once">Once</ToggleButton>
          </ToggleButtonGroup>
        </div>

        {schedType === 'weekly' && <>
          <div>
            <FormLabel>{t('settings.alarms.dialog.days')}</FormLabel>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
              {Object.keys(PRESETS).map(p => (
                <Button key={p} size="small" variant="outlined"
                  onClick={() => patch('schedule.days', [...PRESETS[p]])}>
                  {t(`settings.alarms.dialog.presets.${p}`)}
                </Button>
              ))}
            </div>
            <FormGroup row sx={{ mt: 1 }}>
              {DAY_KEYS.map((day, idx) => (
                <FormControlLabel key={day}
                  control={
                    <Checkbox size="small"
                      checked={days[idx] ?? false}
                      onChange={() => toggleDay(idx)} />
                  }
                  label={t(`settings.alarms.days-short.${day}`)} />
              ))}
            </FormGroup>
          </div>
          <TextField label={t('settings.alarms.dialog.end-date')} type="date" size="small"
            InputLabelProps={{ shrink: true }}
            value={cfg.schedule?.end_date ?? ''}
            onChange={e => patch('schedule.end_date', e.target.value || null)} />
        </>}

        {schedType === 'once' && (
          <TextField label={t('settings.alarms.dialog.once-date')} type="date" size="small"
            InputLabelProps={{ shrink: true }}
            value={cfg.schedule?.date ?? ''}
            onChange={e => patch('schedule.date', e.target.value)} />
        )}

        <TextField label={t('settings.alarms.dialog.content-card-id')} size="small" fullWidth
          value={cfg.content?.card_id ?? ''}
          onChange={e => patch('content.card_id', e.target.value)}
          helperText="RFID card ID (leave empty to use fallback)" />

        <FormControlLabel
          control={<Switch checked={cfg.volume?.fade_in ?? false}
            onChange={e => patch('volume.fade_in', e.target.checked)} />}
          label={t('settings.alarms.dialog.fade-in')} />

        <div>
          <Typography variant="caption">
            {t('settings.alarms.dialog.start-volume')}: {cfg.volume?.start ?? 0}%
          </Typography>
          <Slider value={cfg.volume?.start ?? 0} min={0} max={100} step={5}
            onChange={(_, v) => patch('volume.start', v)} />
        </div>

        <div>
          <Typography variant="caption">
            {t('settings.alarms.dialog.target-volume')}: {cfg.volume?.target ?? 70}%
          </Typography>
          <Slider value={cfg.volume?.target ?? 70} min={0} max={100} step={5}
            onChange={(_, v) => patch('volume.target', v)} />
        </div>

        <Select size="small" value={cfg.max_duration ?? 0}
          onChange={e => patch('max_duration', e.target.value || null)}>
          <MenuItem value={0}>{t('settings.alarms.dialog.max-duration-off')}</MenuItem>
          <MenuItem value={1800}>30 min</MenuItem>
          <MenuItem value={3600}>60 min</MenuItem>
          <MenuItem value={5400}>90 min</MenuItem>
          <MenuItem value={7200}>120 min</MenuItem>
        </Select>

        <Select size="small" value={cfg.snooze_duration ?? 0}
          onChange={e => patch('snooze_duration', e.target.value || null)}>
          <MenuItem value={0}>{t('settings.alarms.dialog.snooze-off')}</MenuItem>
          <MenuItem value={300}>5 min</MenuItem>
          <MenuItem value={600}>10 min</MenuItem>
          <MenuItem value={900}>15 min</MenuItem>
        </Select>

        <Select size="small" value={cfg.post_alarm ?? 'stop'}
          onChange={e => patch('post_alarm', e.target.value)}>
          <MenuItem value="stop">{t('settings.alarms.dialog.post-alarm-stop')}</MenuItem>
          <MenuItem value="resume">{t('settings.alarms.dialog.post-alarm-resume')}</MenuItem>
        </Select>

      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('settings.alarms.dialog.cancel')}</Button>
        <Button onClick={() => onSave(cfg)} variant="contained">
          {t('settings.alarms.dialog.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AlarmDialog;
