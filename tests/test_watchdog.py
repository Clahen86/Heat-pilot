"""Thermostats that don't obey: one room is a valve, two rooms on the same radio is the radio."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from heat_pilot.alerts import text
from heat_pilot.watchdog import Watchdog, disobeying

T0 = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)


def rooms(*names, platform="mqtt"):
    return [{"area_id": n, "name": n.title(), "thermostats": [{"entity_id": f"climate.{n}", "platform": platform}]} for n in names]


def call(n, t):
    return {"calls": [{"service": "set_temperature", "data": {"entity_id": f"climate.{n}", "temperature": t}}]}


def test_two_rooms_on_one_radio_for_20_minutes():
    rs = rooms("stue", "krea", "silas")
    now_rooms = {"stue": call("stue", 21), "krea": call("krea", 20), "silas": call("silas", 20)}
    states = {"climate.stue": {"state": "heat", "attributes": {"temperature": 17}},   # told 21, still 17
              "climate.krea": {"state": "unavailable"},                               # gone
              "climate.silas": {"state": "heat", "attributes": {"temperature": 20}}}  # obeys
    sent = {"climate.stue": (21.0, T0), "climate.krea": (20.0, T0), "climate.silas": (20.0, T0)}
    bad = disobeying(rs, now_rooms, states, sent, lambda v: None if v is None else float(v), lambda a: True)
    assert sorted(e for _, e, _ in bad) == ["climate.krea", "climate.stue"]
    w = Watchdog({})
    assert w.see(bad, T0) == {}  # not yet
    assert w.see(bad, T0 + timedelta(minutes=20)) == {"mqtt": ["Krea", "Stue"]}
    assert w.see(bad[:1], T0 + timedelta(minutes=21)) == {}  # one room: a valve, not the radio
    assert disobeying(rs, now_rooms, states, sent, float, lambda a: False) == []  # shadow: nothing sent, nothing lost
    assert "Krea, Stue" in text({"kind": "not_obeying_restart", "rooms": "Krea, Stue", "radio": "Zigbee2MQTT"}, "da")


def test_restart_once_in_two_hours_and_the_right_radio():
    calls = []

    async def call_service(d, s, data):
        calls.append((d, s, data))

    async def command(m):
        if m["type"] == "config/device_registry/list":
            return [{"identifiers": [["hassio", "45df7312_zigbee2mqtt"]]}, {"identifiers": [["mqtt", "x"]]}]
        return [{"entry_id": "zha1"}]

    ha = SimpleNamespace(call_service=call_service, command=command)
    w = Watchdog({})
    assert w.due("mqtt", T0) and not w.due("tado", T0)  # a cloud: only the warning
    assert asyncio.run(w.restart(ha, "mqtt", T0)) == "Zigbee2MQTT"
    assert calls[-1] == ("hassio", "addon_restart", {"addon": "45df7312_zigbee2mqtt"})
    assert not w.due("mqtt", T0 + timedelta(hours=1)) and w.due("mqtt", T0 + timedelta(hours=2))
    assert asyncio.run(w.restart(ha, "zha", T0)) == "ZHA"
    assert calls[-1] == ("homeassistant", "reload_config_entry", {"entry_id": "zha1"})
