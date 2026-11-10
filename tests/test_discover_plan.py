"""Rooms are found from Home Assistant's areas, and each room's target follows windows, presence and time."""

from datetime import datetime, timedelta, timezone

from heat_pilot import discover, plan

NOW = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)


def st(state="20", **attrs):
    return {"state": state, "attributes": attrs, "last_changed": (NOW - timedelta(hours=2)).isoformat()}


AREAS = [{"area_id": "stue", "name": "Stue"}, {"area_id": "bad", "name": "Badeværelse"}, {"area_id": "gang", "name": "Gang"}]
DEVS = [{"id": "trv1", "area_id": "stue", "model": "TRVZB", "manufacturer": "SONOFF"},
        {"id": "w100", "area_id": "stue", "model": "W100"}, {"id": "floor", "area_id": "bad", "model": "Floor thermostat"}]
ENTS = [{"entity_id": "climate.stue", "device_id": "trv1", "platform": "mqtt"},
        {"entity_id": "sensor.trv_temperature", "device_id": "trv1"},  # the valve's own - not the room's
        {"entity_id": "sensor.stue_termostat_styring_temperatur", "device_id": "w100"},
        {"entity_id": "sensor.stue_ude_temperatur", "area_id": "stue"},
        {"entity_id": "binary_sensor.stue_vindue", "area_id": "stue"},
        {"entity_id": "binary_sensor.stue_motion", "area_id": "stue"},
        {"entity_id": "climate.bad_gulvvarme", "device_id": "floor", "platform": "mqtt"},
        {"entity_id": "climate.group", "area_id": "stue", "platform": "climate_group_helper"},
        {"entity_id": "climate.loose", "platform": "tado"},
        {"entity_id": "sensor.gang_temp", "area_id": "gang"}]
STATES = {"climate.stue": st("heat", hvac_modes=["off", "heat"]), "sensor.trv_temperature": st(device_class="temperature"),
          "sensor.stue_termostat_styring_temperatur": st("21.4", device_class="temperature"),
          "sensor.stue_ude_temperatur": st("5", device_class="temperature"),
          "binary_sensor.stue_vindue": st("off", device_class="window"), "binary_sensor.stue_motion": st("off", device_class="motion"),
          "climate.bad_gulvvarme": st("heat", hvac_modes=["heat"]), "climate.group": st("heat"), "climate.loose": st("heat"),
          "sensor.gang_temp": st(device_class="temperature")}


def test_rooms_found():
    rooms = {r["area_id"]: r for r in discover.find(AREAS, DEVS, ENTS, STATES)}
    assert set(rooms) == {"stue", "bad"}  # no thermostat in the hall
    s = rooms["stue"]
    assert [t["entity_id"] for t in s["thermostats"]] == ["climate.stue"]  # never the group too
    assert s["thermostats"][0]["brand"] == "SONOFF TRVZB"
    assert s["temp_sensor"] == "sensor.stue_termostat_styring_temperatur"  # not the valve's own, not outdoor
    assert s["windows"] == ["binary_sensor.stue_vindue"] and s["presence"] == ["binary_sensor.stue_motion"]
    assert s["kind"] == "living"
    assert rooms["bad"]["kind"] == "bathroom" and rooms["bad"]["heating"] == "floor"
    assert discover.unplaced(ENTS, DEVS, STATES) == ["climate.loose"]


def room(**kw):
    return {"kind": "living", "windows": ["binary_sensor.w"], "presence": ["binary_sensor.m"], **kw}


def test_window_open_turns_off_after_five_minutes():
    s = {"binary_sensor.w": {"state": "on", "last_changed": (NOW - timedelta(minutes=6)).isoformat()}}
    assert plan.target(room(), {}, s, NOW, False, None)["temp"] is None
    s["binary_sensor.w"]["last_changed"] = (NOW - timedelta(minutes=2)).isoformat()
    assert plan.target(room(), {}, s, NOW, False, None)["why"] == "comfort"


def test_day_night_away():
    assert plan.target(room(), {}, {}, NOW, False, None) == {"temp": 21.0, "why": "comfort", "until": NOW.replace(hour=22).isoformat()}
    assert plan.target(room(), {}, {}, NOW.replace(hour=23), False, None)["why"] == "night"
    assert plan.target(room(), {}, {}, NOW, True, None)["temp"] == 17.0
    assert plan.target(room(kind="bedroom"), {}, {}, NOW, False, None)["why"] == "setback"


def test_house_away_needs_an_hour_without_motion():
    rooms = [room()]
    s = {"binary_sensor.m": {"state": "off", "last_changed": (NOW - timedelta(minutes=70)).isoformat()}}
    assert plan.house_away(rooms, s, NOW, None)
    s["binary_sensor.m"]["last_changed"] = (NOW - timedelta(minutes=20)).isoformat()
    assert not plan.house_away(rooms, s, NOW, None)
    assert not plan.house_away([{"presence": []}], {}, NOW, None)  # no sensors: never "away"
