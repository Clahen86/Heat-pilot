"""Hot water: hot when cheap, cool when dear (never below the lowest), warm before the showers, weekly against legionella."""

from datetime import datetime, timedelta, timezone

from heat_pilot.hotwater import calls, decide, find

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
WH = {"water_heater.vvb": {"state": "eco", "attributes": {"current_temperature": 50, "temperature": 52, "min_temp": 30, "max_temp": 75}}}


def d(level, state=None, cfg=None, states=None, now=NOW):
    return decide({"entity": "water_heater.vvb", "ready": [], **(cfg or {})}, state if state is not None else {"hot": NOW.isoformat()},
                  states or WH, level, now)


def test_cheap_dear_normal():
    assert d("cheap")["target"] == 60 and d("dear")["target"] == 45 and d("mid")["target"] == 52


def test_water_heater_call():
    assert d("cheap")["calls"] == [{"domain": "water_heater", "service": "set_temperature", "data": {"entity_id": "water_heater.vvb", "temperature": 60}}]
    assert d("mid")["calls"] == []  # already 52


def test_ready_before_shower_beats_dear():
    assert d("dear", cfg={"ready": ["13:00"]})["why"] == "ready"


def test_legionella_on_cheap_after_a_week():
    old = {"hot": (NOW - timedelta(days=7, hours=1)).isoformat()}
    assert d("cheap", old)["why"] == "legionella"
    assert d("dear", old)["why"] == "dear"  # waits for a cheap hour …
    older = {"hot": (NOW - timedelta(days=8, hours=1)).isoformat()}
    assert d("dear", older)["why"] == "legionella"  # … at most one day


def test_hot_enough_remembered():
    st = {}
    d("mid", st, states={"water_heater.vvb": {"state": "eco", "attributes": {"current_temperature": 65}}})
    assert st["hot"] == NOW.isoformat()


def test_switch_with_sensor_hysteresis():
    s = {"switch.elpatron": {"state": "off"}}
    assert calls("switch.elpatron", 60, 50, "cheap", s)[0]["service"] == "turn_on"
    assert calls("switch.elpatron", 60, 59, "cheap", s) == []
    assert calls("switch.elpatron", 45, 50, "dear", {"switch.elpatron": {"state": "on"}})[0]["service"] == "turn_off"


def test_switch_without_sensor_only_off_when_dear():
    assert calls("switch.elpatron", 45, None, "dear", {"switch.elpatron": {"state": "on"}})[0]["service"] == "turn_off"
    assert calls("switch.elpatron", 52, None, "normal", {"switch.elpatron": {"state": "on"}}) == []


def test_find():
    f = find({**WH, "switch.elpatron": {"state": "on", "attributes": {}}, "switch.lamp": {"state": "on"},
              "sensor.vvb_temp": {"state": "55", "attributes": {"device_class": "temperature"}}})
    assert [x["entity_id"] for x in f["heaters"]] == ["water_heater.vvb"]
    assert [x["entity_id"] for x in f["switches"]] == ["switch.elpatron"]
    assert [x["entity_id"] for x in f["temps"]] == ["sensor.vvb_temp"]
