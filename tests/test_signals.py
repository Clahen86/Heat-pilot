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


def test_lost_room_sensor_puts_the_valve_back_on_its_own_sensor():
    from types import SimpleNamespace

    from heat_pilot.engine import Pilot

    p = Pilot.__new__(Pilot)
    p.ha = SimpleNamespace(states={
        "sensor.room": {"state": "unavailable", "last_updated": T0.isoformat()},
        "number.v_external_temperature_input": {"state": "22.54"},
        "select.v_sensor": {"state": "external", "attributes": {"options": ["internal", "external"]}},
    })
    r = {"area_id": "bad", "temp_sensor": "sensor.room", "thermostats": [{"entity_id": "climate.v",
         "profile": {"room_sensor": ("external_temperature_input", "sensor", "external")}}]}
    assert p.room_sensor_calls(r, T0) == []  # just gone: a sensor often blinks
    assert not p.sensor_lost(r, T0 + timedelta(minutes=10))
    calls = p.room_sensor_calls(r, T0 + timedelta(minutes=15))
    assert calls == [{"domain": "select", "service": "select_option", "data": {"entity_id": "select.v_sensor", "option": "internal"}}]
    p.ha.states["select.v_sensor"]["state"] = "internal"
    assert p.room_sensor_calls(r, T0 + timedelta(minutes=20)) == []  # done once, no old number sent
    p.ha.states["sensor.room"] = {"state": "21.0", "last_updated": (T0 + timedelta(minutes=25)).isoformat()}
    assert not p.sensor_lost(r, T0 + timedelta(minutes=25))  # back: normal again
    assert {"domain": "select", "service": "select_option", "data": {"entity_id": "select.v_sensor", "option": "external"}} \
        in p.room_sensor_calls(r, T0 + timedelta(minutes=25))


def test_lost_room_sensor_alert_says_safe_mode():
    from heat_pilot import alerts

    a = {"kind": "sensor_lost", "room": "Badeværelse kælder", "device": "Føler", "safe": True, "temp": 18.0}
    assert "18.0°" in alerts.text(a, "da") and "Gulvvarmen" in alerts.text(a, "da")
    assert "own sensor" in alerts.text({**a, "safe": False}, "en")
    for lang in ("da", "en", "de", "fr", "nl", "sv", "nb"):
        assert alerts.text(a, lang) and alerts.text({**a, "safe": False}, lang)


def test_card_hold_and_boost_are_never_learned_from():
    from types import SimpleNamespace

    from heat_pilot.engine import Pilot

    p = Pilot.__new__(Pilot)
    p.ha = SimpleNamespace(config={"time_zone": "Europe/Copenhagen", "unit_system": {"temperature": "°C"}}, states={})
    p.watch = Watch()
    p.now = {"r": {"want": {"temp": 18.0, "why": "setback"}}}
    p.rooms = lambda: [{"area_id": "r", "cfg": {"comfort": 20.0}}]
    b = p.hold("r", boost=True)
    assert b["temp"] == 22.0 and b["boost"]  # comfort + 2
    assert p.watch.manual["r"]["card"]
    s = p.hold("r", step=-0.5)
    assert s["temp"] == 21.5 and not s["boost"]  # a step from the hold now
    assert p.hold("r", temp=40)["temp"] == 28.0  # kept sane
    assert p.hold("nowhere", boost=True) is None
    p.resume("r")
    assert "r" not in p.watch.manual


def test_sonoff_with_newer_zigbee2mqtt_names():
    # Hobby: "Zigbee thermostatic radiator valve" by SONOFF, parts named after the device, not the climate
    from types import SimpleNamespace

    from heat_pilot import brands
    from heat_pilot.engine import Pilot

    prof = brands.profile("mqtt", "Zigbee thermostatic radiator valve", "SONOFF")
    assert prof["name"] == "SONOFF TRVZB"
    p = Pilot.__new__(Pilot)
    p.ha = SimpleNamespace(states={
        "sensor.room": {"state": "17.76", "last_updated": T0.isoformat()},
        "number.termostat_hobby_external_temperature_sensor_value": {"state": "17.8"},
        "select.termostat_hobby_temperature_sensor": {"state": "local_temperature",
                                                      "attributes": {"options": ["local_temperature", "remote_temperature", "remote_source_offline"]}},
    })
    r = {"temp_sensor": "sensor.room", "thermostats": [{"entity_id": "climate.termostat_hobby_termostat", "profile": prof}]}
    calls = p.room_sensor_calls(r, T0)
    assert {"domain": "select", "service": "select_option",
            "data": {"entity_id": "select.termostat_hobby_temperature_sensor", "option": "remote_temperature"}} in calls
    assert {"domain": "number", "service": "set_value",
            "data": {"entity_id": "number.termostat_hobby_external_temperature_sensor_value", "value": 17.76}} in calls


def test_a_valve_falling_back_to_its_old_setpoint_is_not_by_hand():
    # An Aqara E1 took 22 and reported its old 17 again minutes later: it was copied to the room's other valves as "by hand"
    w = Watch()
    w.see_setpoint("stue", "climate.c", 17.0, T0, True)
    w.wrote("climate.c", 22.0, T0 + timedelta(minutes=1))
    w.see_setpoint("stue", "climate.c", 22.0, T0 + timedelta(minutes=1), True)  # echo
    w.see_setpoint("stue", "climate.c", 17.0, T0 + timedelta(minutes=5), True)  # fell back
    assert w.manual_for("stue", T0 + timedelta(minutes=5)) is None
    w.see_setpoint("stue", "climate.c", 22.0, T0 + timedelta(minutes=6), True)
    w.see_setpoint("stue", "climate.c", 17.0, T0 + timedelta(minutes=30), True)  # long after: a person
    assert w.manual_for("stue", T0 + timedelta(minutes=30))["temp"] == 17.0
