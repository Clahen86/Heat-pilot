"""Signs from the house: CO2/humidity/lights, showers, the sun, the front door and turning by hand."""

from datetime import datetime, timedelta, timezone

from heat_pilot import features, plan
from heat_pilot.signals import Watch

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def st(v, **a):
    return {"state": str(v), "attributes": a, "last_changed": T0.isoformat()}


def run(w, room, series, key, minutes=1):
    for i, v in enumerate(series):
        w.see(room, {key: st(v)}, T0 + timedelta(minutes=i * minutes), False, 20.0)


def test_shower_holds_bathroom_warm():
    w, room = Watch(), {"area_id": "bad", "kind": "bathroom", "humidity": ["sensor.h"]}
    run(w, room, [55, 56, 58, 63, 66], "sensor.h")
    assert w.shower("bad", T0 + timedelta(minutes=10))
    assert not w.shower("bad", T0 + timedelta(minutes=70))
    assert plan.target({"kind": "bathroom", "windows": []}, {}, {}, T0.replace(hour=10), False, None, [], 19.0, 12, shower=True)["why"] == "shower"


def test_co2_rise_and_light_mean_someone():
    w, room = Watch(), {"area_id": "stue", "kind": "living", "co2": ["sensor.c"], "humidity": [], "lights": ["light.l"]}
    for i, v in enumerate([600, 620, 660, 700, 720]):
        w.see(room, {"sensor.c": st(v)}, T0 + timedelta(minutes=2 * i), False, 20.0)
    assert w.someone(room, {})
    w2 = Watch()
    w2.see(room, {"sensor.c": st(600)}, T0, False, 20.0)
    assert not w2.someone(room, {"light.l": st("off")})
    assert w2.someone(room, {"light.l": st("on")})


def test_bathroom_humidity_is_not_someone():
    w, room = Watch(), {"area_id": "bad", "kind": "bathroom", "humidity": ["sensor.h"]}
    run(w, room, [50, 52, 54], "sensor.h")
    assert not w.someone(room, {})


def test_manual_only_where_controlled_and_never_an_echo_or_frost():
    w = Watch()
    w.see_setpoint("stue", "climate.a", 20.0, T0, True)
    w.see_setpoint("stue", "climate.a", 22.0, T0 + timedelta(minutes=1), False)  # shadow: AppDaemon changed it
    assert w.manual_for("stue", T0 + timedelta(minutes=2)) is None
    w.wrote("climate.a", 19.0, T0 + timedelta(minutes=3))
    w.see_setpoint("stue", "climate.a", 19.0, T0 + timedelta(minutes=4), True)  # our echo
    assert w.manual_for("stue", T0 + timedelta(minutes=4)) is None
    w.see_setpoint("stue", "climate.a", 5.0, T0 + timedelta(minutes=5), True)  # frost fallback
    assert w.manual_for("stue", T0 + timedelta(minutes=5)) is None
    w.see_setpoint("stue", "climate.a", 23.0, T0 + timedelta(minutes=6), True)  # a person
    m = w.manual_for("stue", T0 + timedelta(minutes=7))
    assert m and m["temp"] == 23.0
    assert w.manual_for("stue", T0 + timedelta(minutes=70)) is None


def test_front_door_then_no_motion_means_away():
    w = Watch()
    s = {"binary_sensor.door": {"state": "off", "last_changed": T0.isoformat()}}
    assert not w.door_away(["binary_sensor.door"], s, T0 + timedelta(minutes=5), T0 - timedelta(minutes=1))
    assert w.door_away(["binary_sensor.door"], s, T0 + timedelta(minutes=11), T0 - timedelta(minutes=1))
    assert not w.door_away(["binary_sensor.door"], s, T0 + timedelta(minutes=11), T0 + timedelta(minutes=3))


def test_sun_delays_preheat():
    room = {"kind": "living", "windows": []}
    at = T0.replace(hour=16, minute=40)
    assert plan.target(room, {}, {}, at, False, None, [17], 18.0, 12.0)["why"] == "preheat"
    assert plan.target(room, {}, {}, at, False, None, [17], 18.0, 12.0, sun=True)["why"] == "sun"


def test_features_hidden_when_missing_and_can_be_turned_off():
    have = features.found([{"kind": "living", "thermostats": [1], "presence": []}], {}, [])
    assert have == {"signals": False, "shower": False, "sun": False, "weather": False, "door": False, "manual": True,
                    "people": False, "holiday": False, "summer": False, "district": False, "price": False, "ventilation": False, "strategy": True, "floor": False, "doors": False}
    on = features.active({"features": {"manual": False}}, have)
    assert not on["manual"]


def test_a_valve_swapping_sensor_is_not_turning_by_hand():
    """Aqara E1: it lost the room sensor for a moment, fell back to its own and copied an old setpoint (18 -> 20)."""
    from heat_pilot.engine import sensor_switched

    now = T0 + timedelta(minutes=1)
    states = {"select.holly_thermostat_sensor": {"state": "external", "last_changed": (T0 + timedelta(seconds=6)).isoformat()}}
    assert sensor_switched(states, "climate.holly_thermostat", now)
    assert not sensor_switched(states, "climate.holly_thermostat", now + timedelta(minutes=10))
    assert not sensor_switched({}, "climate.holly_thermostat", now)
    w = Watch()
    w.see_setpoint("holly", "climate.holly_thermostat", 18.0, T0, True)
    w.see_setpoint("holly", "climate.holly_thermostat", 20.0, now, True, sensor_switched(states, "climate.holly_thermostat", now))
    assert w.manual_for("holly", now) is None


def test_room_temperature_sent_to_the_valve_every_five_minutes():
    from types import SimpleNamespace

    from heat_pilot.engine import Pilot

    p = Pilot.__new__(Pilot)
    now = T0
    p.ha = SimpleNamespace(states={
        "sensor.room": {"state": "20.4", "last_updated": (now - timedelta(hours=3)).isoformat()},
        "number.v_external_temperature_input": {"state": "19"},
        "select.v_sensor": {"state": "internal"},
    })
    r = {"temp_sensor": "sensor.room", "thermostats": [{"entity_id": "climate.v",
         "profile": {"room_sensor": ("external_temperature_input", "sensor", "external")}}]}
    calls = p.room_sensor_calls(r, now)
    assert {"domain": "select", "service": "select_option", "data": {"entity_id": "select.v_sensor", "option": "external"}} in calls
    assert {"domain": "number", "service": "set_value", "data": {"entity_id": "number.v_external_temperature_input", "value": 20.4}} in calls
    assert [c for c in p.room_sensor_calls(r, now + timedelta(minutes=2)) if c["domain"] == "number"] == []  # not yet
    assert [c for c in p.room_sensor_calls(r, now + timedelta(minutes=5)) if c["domain"] == "number"]  # also when it stands still
    p.ha.states["sensor.room"]["last_updated"] = (now - timedelta(hours=13)).isoformat()
    assert p.room_sensor_calls(r, now + timedelta(minutes=10)) == []  # a sensor gone quiet: the valve uses its own
    assert p.room_sensor_calls({**r, "temp_sensor": None}, now) == []  # no room sensor: never its own reading fed back
