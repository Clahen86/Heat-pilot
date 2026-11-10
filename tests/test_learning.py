"""Learning when rooms are used and how fast they heat - and starting the heat in time."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from heat_pilot import plan
from heat_pilot.learning import Learning, seed

MON = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)  # a Monday


def test_seed_from_history_and_pool_workdays(tmp_path: Path):
    l = Learning(tmp_path)
    # Ten days: someone in the room 17-21 every day, a short visit at 14:20.
    iv = []
    for d in range(10):
        day = MON - timedelta(days=10) + timedelta(days=d)
        iv += [(day.replace(hour=h, minute=m), day.replace(hour=h, minute=m, second=30)) for h in range(17, 21) for m in range(0, 60, 5)]
        iv.append((day.replace(hour=14, minute=20), day.replace(hour=14, minute=21)))
        iv.append((day.replace(hour=2, minute=0), day.replace(hour=5, minute=0)))  # a sleeper at night
    seed(l, "stue", iv, MON - timedelta(days=10), MON)
    hours = l.hours("stue", 0)
    assert hours == [17, 18, 19, 20]  # pooled with the other workdays; the night never counts, nor a short visit
    assert l.known("stue") == 168


def test_lone_gap_is_kept_warm(tmp_path: Path):
    l = Learning(tmp_path)
    for h in range(24):
        l.s["use"].setdefault("r", {})[f"0_{h}"] = {"m": 0, "on": 0, "days": ["a", "b", "c"], "p": 0.6 if h in (7, 9) else 0.0}
    assert l.hours("r", 0) == [7, 8, 9]


def test_heat_rate_learned(tmp_path: Path):
    l = Learning(tmp_path)
    t = MON.replace(hour=6)
    l.see_heating("r", t, True, 18.0, 21.0, "radiator")
    l.see_heating("r", t + timedelta(minutes=45), True, 20.8, 21.0, "radiator")
    assert l.rate("r", "radiator") == (16.1, 1)  # 45 min / 2.8 °C
    assert l.rate("other", "floor") == (35.0, 0)


def test_preheat_starts_in_time():
    room = {"kind": "living", "windows": []}
    hours = [17, 18, 19, 20]
    at = MON.replace(hour=16, minute=10)
    # 3 °C to go at 12 min/°C = 36 min: from 16:24 - not yet at 16:10, but at 16:30.
    assert plan.target(room, {}, {}, at, False, None, hours, 18.0, 12.0)["why"] == "setback"
    assert plan.target(room, {}, {}, at.replace(minute=30), False, None, hours, 18.0, 12.0)["why"] == "preheat"
    assert plan.target(room, {}, {}, at, False, None, hours, 18.0, 12.0, occupied=True)["why"] == "occupied"
