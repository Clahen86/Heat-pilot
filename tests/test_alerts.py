"""Warnings: shown always, sent only when chosen - each kind can be turned off, never spammed."""

from datetime import datetime, timedelta, timezone

from heat_pilot.alerts import Alerts, text

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def room(**kw):
    return {"area_id": "r", "name": "Krea", "kind": "kids", "humidity": ["sensor.h"], "co2": ["sensor.c"], "windows": ["binary_sensor.w"],
            "thermostats": [{"entity_id": "climate.t", "name": "Termostat"}], "batteries": ["sensor.b"], **kw}


def st(h=50, c=600, w="off", wmin=0, t="heat", tmin=0, b=80):
    return {"sensor.h": {"state": str(h)}, "sensor.c": {"state": str(c)}, "sensor.b": {"state": str(b), "attributes": {"friendly_name": "Termostat batteri"}},
            "binary_sensor.w": {"state": w, "last_changed": (NOW - timedelta(minutes=wmin)).isoformat()},
            "climate.t": {"state": t, "last_changed": (NOW - timedelta(minutes=tmin)).isoformat()}}


def kinds(a):
    return sorted(x["kind"] for x in a.active)


def test_quiet_house_no_warnings():
    a = Alerts({})
    a.check([room()], {"r": {"temp": 20.0}}, st(), NOW, 5.0, None)
    assert a.active == []


def test_each_warning():
    a = Alerts({})
    a.check([room()], {"r": {"temp": 15.0}}, st(h=66, w="on", wmin=40, t="unavailable", tmin=45, b=10), NOW, 5.0, None)
    assert kinds(a) == ["battery", "mold", "offline", "window"]  # cold and damp: mould at once
    a.check([room()], {"r": {"temp": 20.0}}, st(c=1300), NOW, 5.0, None)
    a.check([room()], {"r": {"temp": 20.0}}, st(c=1300), NOW + timedelta(minutes=31), 5.0, None)
    assert kinds(a) == ["air"]
    a.check([room()], {"r": {"temp": 18.0, "want": {"temp": 21.0}, "heating": True}}, st(), NOW, 5.0, None)
    a.check([room()], {"r": {"temp": 18.2, "want": {"temp": 21.0}, "heating": True}}, st(), NOW + timedelta(hours=3), 5.0, None)
    assert kinds(a) == ["not_warming"]


def test_sent_only_when_chosen_not_twice_not_at_night_and_kinds_off():
    a = Alerts({})
    a.check([room()], {"r": {"temp": 20.0}}, st(b=5), NOW, 5.0, None)
    assert a.to_send({}, NOW) == []  # nobody chosen
    cfg = {"messages": {"targets": ["mobile_app_phone"]}}
    assert len(a.to_send(cfg, NOW)) == 1
    assert a.to_send(cfg, NOW + timedelta(hours=1)) == []  # not again so soon
    b = Alerts({})
    b.check([room()], {"r": {"temp": 20.0}}, st(b=5), NOW, 5.0, None)
    assert b.to_send(cfg, NOW.replace(hour=23)) == []  # night
    assert b.to_send({"messages": {"targets": ["x"], "kinds": {"battery": False}}}, NOW) == []  # turned off


def test_texts():
    assert "Krea" in text({"kind": "air", "room": "Krea", "co2": 1300}, "da")
    assert text({"kind": "battery", "device": "Termostat", "level": 9}, "en") == "Termostat has 9 % left – change the battery."


def test_monthly_text():
    t = text({"kind": "monthly", "month": "2026-11", "degree_hours": 420, "pct": 8.5, "ontime": 92}, "da")
    assert "8.5 %" in t and "gradtimer" not in t


def test_too_warm_for_six_hours_is_a_valve_not_closing():
    a = Alerts({})
    hot = {"r": {"temp": 23.0, "want": {"temp": 18.0}}}
    a.check([room()], hot, st(), NOW, 5.0, None)
    a.check([room()], hot, st(), NOW + timedelta(hours=5), 5.0, None)
    assert "too_warm" not in kinds(a)  # the sun can do a few hours
    a.check([room()], hot, st(), NOW + timedelta(hours=6), 5.0, None)
    assert kinds(a) == ["too_warm"]
    a.check([room()], hot, st(), NOW + timedelta(hours=7), 18.0, None)
    assert kinds(a) == []  # a warm day outside: not the valve
    assert "Krea" in text({"kind": "too_warm", "room": "Krea", "temp": 23.0, "want": 18.0}, "da")


def test_rechargeable_cells_are_not_a_low_battery():
    a = Alerts({})
    s = {**st(b=5), "sensor.thermo_battery": {"state": "5", "attributes": {"friendly_name": "Batteri"}},
         "sensor.thermo_voltage": {"state": "2700", "attributes": {"unit_of_measurement": "mV"}}}
    a.check([room(batteries=["sensor.thermo_battery"])], {"r": {"temp": 20.0}}, s, NOW, 5.0, None)
    assert a.active == []  # 2 x 1.35 V: full NiMH cells, though the valve says 5 %
    s["sensor.thermo_voltage"]["state"] = "2100"
    a.check([room(batteries=["sensor.thermo_battery"])], {"r": {"temp": 20.0}}, s, NOW, 5.0, None)
    assert kinds(a) == ["battery"]  # 1.05 V a cell: really empty
