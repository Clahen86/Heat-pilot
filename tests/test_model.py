"""The rest from AppDaemon, made general: evening comfort, room model, sun, strategies, floors, doors, no-show."""

from datetime import datetime, timedelta, timezone

from heat_pilot import discover, plan
from heat_pilot.learning import Model

NOW = datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)
LIVING = {"kind": "living", "windows": []}


def test_evening_comfort():
    cfg = {"evening": 22.0, "evening_from": 15, "evening_to": 22}
    w = plan.target(LIVING, cfg, {}, NOW, False, None)
    assert w["temp"] == 22.0 and w["why"] == "comfort_evening"
    assert plan.target(LIVING, cfg, {}, NOW.replace(hour=10), False, None)["temp"] == 21.0


def test_room_model_learns_heat_loss_and_short_gaps_stay_warm():
    m = Model({})
    t0 = NOW.replace(hour=1)
    for i in range(40):  # heating off at night: 21 -> 20.5 over 40 min with 1° outside
        m.see("r", t0 + timedelta(minutes=i), 21.0 - 0.5 * i / 40, 1.0, False, False, False)
    k = m.loss("r")
    assert k and 0.01 < k < 0.05
    assert m.drop("r", 21.0, 1.0, 0.5) < 0.5 < m.drop("r", 21.0, 1.0, 1.0)  # half an hour hardly cools it; an hour does
    w = plan.target(LIVING, {}, {}, NOW.replace(hour=23), False, None, extra={"hold_warm": True})
    assert w["why"] == "night"  # never at night
    assert plan.target({"kind": "kids", "windows": []}, {}, {}, NOW.replace(hour=22, minute=30), False, None, [23], 20.0, 12.0)["why"] != "hold"


def test_sun_learned_and_used_ahead():
    m = Model({})
    t0 = NOW.replace(hour=11)
    for i in range(40):
        m.see("r", t0 + timedelta(minutes=i), 19.0 + 0.6 * i / 40, 5.0, False, True, True)
    assert m.sun_gain("r", NOW.replace(hour=11), 1) > 0.5
    room = {"kind": "living", "windows": []}
    w = plan.target(room, {}, {}, NOW.replace(hour=16, minute=50), False, None, [17], 20.0, 12.0, extra={"sun_ahead": 1.0})
    assert plan.target(room, {}, {}, NOW.replace(hour=16, minute=50), False, None, [17], 20.0, 12.0)["why"] == "preheat"
    assert w["why"] == "sun"


def test_strategies_try_each_then_pick_cheapest():
    m = Model({})
    day = NOW.replace(hour=8)
    seen = []
    for d in range(12):
        arm = m.arm_today(day + timedelta(days=7 * d))  # same weekday each time
        seen.append(arm)
        m.see_day(10 if arm == "early" else 5, 1 if arm == "gentle" else 0)
    assert seen[:9] == ["normal"] * 3 + ["early"] * 3 + ["gentle"] * 3
    assert m.arm_today(day + timedelta(days=7 * 12)) in ("normal", "early", "gentle")


def test_floor_door_buffer_noshow():
    floor = {"kind": "bathroom", "heating": "floor", "windows": []}
    assert plan.target(floor, {"day_from": 6, "day_to": 7}, {}, NOW, False, None, extra={"floor_active": True})["why"] == "floor"
    assert plan.target(LIVING, {}, {}, NOW, False, None, extra={"door": True}) == {"temp": 19.0, "why": "door", "until": NOW.replace(hour=22).isoformat()}
    assert plan.target(floor, {}, {}, NOW, False, None, extra={"buffer": True})["temp"] == 23.0
    at = NOW.replace(hour=16, minute=40)
    assert plan.target(LIVING, {}, {}, at, False, None, [17], 18.0, 12.0, extra={"noshow": True})["why"] == "setback"


def test_window_or_door_by_name():
    areas = [{"area_id": "stue", "name": "Stue"}]
    ents = [{"entity_id": "climate.s", "area_id": "stue", "platform": "mqtt"},
            {"entity_id": "binary_sensor.stue_vindue_sensor_dor", "area_id": "stue"},
            {"entity_id": "binary_sensor.stue_udestue_dor", "area_id": "stue"}]
    st = {"climate.s": {"state": "heat", "attributes": {}},
          "binary_sensor.stue_vindue_sensor_dor": {"state": "off", "attributes": {"device_class": "door"}},
          "binary_sensor.stue_udestue_dor": {"state": "off", "attributes": {"device_class": "door"}}}
    r = discover.find(areas, [], ents, st)[0]
    assert r["windows"] == ["binary_sensor.stue_vindue_sensor_dor"] and r["doors"] == ["binary_sensor.stue_udestue_dor"]
