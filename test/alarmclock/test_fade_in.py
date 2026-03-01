import sys, os
sys.path.append(os.path.abspath('src/jukebox'))

import threading
from components.alarmclock.fade_in import FadeIn


def test_generates_correct_steps():
    calls = []
    FadeIn(start=10, target=70, ramp_seconds=0.05, steps=5,
           set_volume_fn=calls.append).run_sync()
    assert len(calls) == 5
    assert calls[0] == 10
    assert calls[-1] == 70
    assert all(calls[i] <= calls[i + 1] for i in range(len(calls) - 1))


def test_start_equals_target():
    calls = []
    FadeIn(start=50, target=50, ramp_seconds=0.01, steps=3,
           set_volume_fn=calls.append).run_sync()
    assert all(v == 50 for v in calls)


def test_clamps_to_valid_range():
    calls = []
    FadeIn(start=0, target=100, ramp_seconds=0.05, steps=5,
           set_volume_fn=calls.append).run_sync()
    assert all(0 <= v <= 100 for v in calls)


def test_cancel_stops_early():
    calls = []
    fade = FadeIn(start=0, target=100, ramp_seconds=0.5, steps=10,
                  set_volume_fn=calls.append)
    t = threading.Thread(target=fade.run_sync)
    t.start()
    import time; time.sleep(0.08)
    fade.cancel()
    t.join(timeout=2)
    assert len(calls) < 10
