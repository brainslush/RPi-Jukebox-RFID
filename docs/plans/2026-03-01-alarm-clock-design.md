# Alarm Clock Feature Design

**Date:** 2026-03-01
**Branch:** alarm_clock
**Status:** Approved

---

## Overview

The alarm clock feature allows users to schedule audio playback at specific times using any content assignable to an RFID card. It supports multiple alarms, flexible recurrence schedules, configurable fade-in, snooze/dismiss via web UI, GPIO buttons, and RFID card scanning.

---

## 1. Component Architecture

A new **`alarmclock`** plugin at `src/jukebox/components/alarmclock/` follows the same pattern as existing components (`timers/`, `playermpd/`).

**Responsibilities:**
- Load/save alarm configurations from `shared/settings/alarmclock.yaml`
- Run a background scheduler thread that sleeps precisely until the next alarm fires
- Execute alarm actions (resolve card content, start playback, fade volume, manage post-alarm state)
- Expose RPC endpoints for CRUD operations and snooze/dismiss
- Publish alarm state via the existing PubSub system

**New dependencies:** None. Uses `threading`, `datetime`, `zoneinfo` (stdlib, Python 3.9+).

The plugin registers itself via `@plugs.register` and initializes via `plugs.finalize()` so it has access to player and volume components after they are loaded.

---

## 2. Data Model

Stored in `shared/settings/alarmclock.yaml`.

### Per-alarm structure

```yaml
alarms:
  alarm_001:
    enabled: true
    label: "Morning wake-up"         # Optional display name
    time: "07:30"                    # HH:MM wall-clock time (24h)
    schedule:
      type: weekly                   # weekly | once
      days: [mon, tue, wed, thu, fri]  # For type: weekly
      end_date: null                 # Optional ISO date: "2026-06-01"
      # For type: once:
      # date: "2026-03-15"
    content:
      card_id: "1234567890"          # RFID card ID resolved via cards.yaml
    volume:
      fade_in: true
      start: 10                      # 0–100 (volume at alarm start)
      target: 70                     # 0–100 (fade-in target volume)
      restore_after: true            # Restore pre-alarm volume on dismiss
    max_duration: 3600               # Seconds until auto-stop; null = no limit
    catch_up_window: 300             # Fire if within N seconds of missed time; 0 = skip
    post_alarm: resume               # resume | stop (what happens to interrupted playback)
    snooze_duration: 600             # Seconds to snooze; null = no snooze
```

### Global settings

```yaml
settings:
  fallback:
    card_id: null          # Card ID to use as fallback (null = use file)
    file: null             # Absolute path to fallback audio file
  timezone: "Europe/Berlin"   # Timezone for wall-clock alarm interpretation
```

---

## 3. Scheduler Logic

A single background daemon thread using `threading.Event.wait(timeout)` for power-efficient sleeping.

```
on start:
  load alarms from YAML
  loop forever:
    next_alarm = find_next_alarm_to_fire(all enabled alarms, now)
    if next_alarm is None:
      wait indefinitely on wakeup_event
    else:
      sleep until next_alarm.fire_time via wakeup_event.wait(timeout)
      if wakeup_event was set (config change):
        continue  # recalculate
      if (now - fire_time) <= catch_up_window:
        fire(next_alarm)
      else:
        log("missed alarm, skipping")
      # recalculate next
```

**Wakeup mechanism:** `threading.Event` is set whenever alarms are added, modified, or deleted. This causes the scheduler to immediately recalculate the next fire time without sleeping through a stale timeout. This is the key mechanism enabling both power efficiency and responsiveness to config changes.

### `next_fire_time(alarm, after_dt)` logic

- **`once`:** Return the scheduled datetime if it is in the future (respects `end_date = date`).
- **`weekly`:** Find the next datetime matching any scheduled weekday at `alarm.time`, after `after_dt`. Respect `end_date`. Return `None` if past end date.
- All datetimes are computed in the configured timezone using `zoneinfo`.

### DST handling

All fire times are calculated using `zoneinfo` (stdlib Python 3.9+). The alarm time is always interpreted as wall-clock time in the configured timezone: "07:30" fires at 07:30 regardless of DST transitions.

### Simultaneous alarms

If multiple alarms are scheduled within the same minute, they are sorted by fire time and executed sequentially. The second alarm fires immediately after the first is dismissed or its `max_duration` expires.

---

## 4. Alarm Execution

### On fire

1. **Save pre-alarm state:** Current player state (playing/paused/stopped, position), current system volume.
2. **Stop current playback** if active (via existing player RPC).
3. **Set volume** to `start` volume (or 0 if fade-in enabled).
4. **Resolve content:** Look up `card_id` in `cards.yaml`.
   - If card ID does not exist → use global fallback.
   - If card ID exists → trigger the card's mapped RPC command (same as scanning the card; no assumptions about what the command does).
5. **Optionally verify playback started:** After ~2 seconds, check `player.status`. If `play` is expected but player is not playing, fall back to global fallback audio. (This check is configurable per alarm.)
6. **Fade-in:** If enabled, ramp volume from `start` to `target` over a configurable ramp duration using a repeating timer loop.
7. **Start max-duration timer** if configured.
8. **Publish active alarm state** via PubSub.

### On dismiss

1. Stop alarm audio and cancel all alarm timers (fade-in, max-duration, snooze).
2. Restore pre-alarm volume if `restore_after: true`.
3. If `post_alarm: resume` → restore previous player state (seek to saved position).
4. If `post_alarm: stop` → leave stopped.
5. Publish cleared alarm state.

### On snooze

1. Pause/stop alarm audio. Cancel active alarm timers.
2. Schedule one-shot re-fire after `snooze_duration` seconds (using `threading.Event.wait`).
3. On re-fire: same execution path as above (re-resolve content, re-fade).
4. Publish snoozed alarm state.

### Dismiss/Snooze triggers

1. **Web UI:** RPC call to `alarmclock.dismiss()` or `alarmclock.snooze()`
2. **GPIO buttons:** Configurable in `jukebox.yaml` using the existing controls component, mapped to `alarmclock.dismiss` / `alarmclock.snooze` RPC calls.
3. **RFID card scan:** The alarm's own card ID (or any card, configurable) triggers snooze or dismiss. Behavior (snooze vs dismiss) is configurable.

---

## 5. RPC Interface

All functions registered via `@plugs.register`:

| Function | Description |
|---|---|
| `alarmclock.list()` | Return dict of all alarms |
| `alarmclock.get(alarm_id)` | Return single alarm config |
| `alarmclock.add(alarm_config)` | Create alarm, return new ID |
| `alarmclock.update(alarm_id, diff)` | Patch alarm fields |
| `alarmclock.delete(alarm_id)` | Delete alarm |
| `alarmclock.set_enabled(alarm_id, enabled)` | Toggle alarm on/off |
| `alarmclock.snooze()` | Snooze active alarm |
| `alarmclock.dismiss()` | Dismiss active alarm |
| `alarmclock.get_next_fire_time()` | ISO datetime of next scheduled alarm |
| `alarmclock.get_active()` | Currently firing alarm info, or null |

---

## 6. PubSub Topics

Published on any relevant state change:

| Topic | Payload |
|---|---|
| `alarmclock.alarms` | Full alarm list (on config change) |
| `alarmclock.active` | `{alarm_id, state: "firing\|snoozed\|null", fire_time, snooze_until}` |
| `alarmclock.next_fire_time` | ISO datetime string of next alarm, or null |

---

## 7. Frontend (React Webapp)

A new **Alarms** section in the Settings panel:

- **List view:** All alarms with enabled toggle, next fire time, edit/delete buttons.
- **Alarm editor modal:**
  - Time picker (HH:MM)
  - Day selector with presets (Daily, Weekdays, Weekends, Custom)
  - Optional end date picker
  - Content picker: browse library | scan RFID card | manual card ID entry
  - Volume settings: fade-in toggle, start %, target %
  - Max playback duration selector (off / 30 / 60 / 90 / 120 min / custom)
  - Snooze duration (off / 5 / 10 / 15 min / custom)
  - Post-alarm behavior (resume / stop)
  - Catch-up window
- **Active alarm overlay/banner:** Dismiss and snooze buttons displayed during active alarm.

**RFID scan-during-setup flow:** A "Scan card" button puts the UI in listening mode (subscribes to the RFID scan PubSub topic). The next card scan populates the card ID field and exits listening mode.

---

## 8. Error Handling & Edge Cases

| Scenario | Handling |
|---|---|
| Card ID not in cards.yaml at alarm time | Use global fallback audio |
| Fallback audio also unavailable | Log error; alarm state published as active (silent alarm) |
| Player does not start after card trigger (optional check) | After ~2s, check player status; fall back if not playing |
| System offline when alarm was due | On startup, check all alarms; fire if within catch-up window |
| NTP time jump forward | Scheduler recalculates on Event wake; fires immediately if within catch-up window |
| NTP time jump backward | Safe: `next_fire_time()` always looks forward from `now` |
| DST transition | Handled by `zoneinfo`; wall-clock time preserved |
| Multiple simultaneous alarms | Sorted and executed sequentially |
| Jukebox restart during active alarm | Active state not persisted; resumes normal operation after restart |

---

## 9. Testing Strategy

- **Unit tests** for `next_fire_time()`: weekly recurrence, once, end dates, DST transitions, catch-up window
- **Unit tests** for alarm execution state machine: fire, snooze, dismiss, post-alarm behavior
- **Integration tests** for RPC endpoints: add/update/delete/enable/disable/snooze/dismiss
- Follow existing test structure in `/test/`

---

## 10. Out of Scope (Initial Version)

- Per-alarm fallback audio (global fallback only)
- Multiple snoozes (single snooze per alarm firing)
- Android/iOS push notifications
- Cloud sync of alarm settings
