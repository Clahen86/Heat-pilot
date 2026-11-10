"""A whole round on a small made-up house: everything wired together runs without errors."""

import asyncio
from datetime import datetime, timedelta, timezone

from heat_pilot.engine import Pilot

NOW = datetime.now(timezone.utc)


def st(state, **a):
    return {"state": str(state), "attributes": a, "last_changed": (NOW - timedelta(minutes=20)).isoformat()}


class FakeHA:
    config = {"time_zone": "Europe/Copenhagen", "language": "da"}

    def __init__(self):
        self.states = {
            "climate.stue": st("heat", hvac_modes=["off", "heat"], preset_modes=["manual", "away"], temperature=21, current_temperature=20.5,
                               hvac_action="heating", min_temp=5, max_temp=30, target_temp_step=0.5),
            "climate.bad": st("heat", hvac_modes=["heat"], temperature=22, current_temperature=21),
            "sensor.stue_temp": st("20.4", device_class="temperature"), "sensor.stue_hum": st("48", device_class="humidity"),
            "sensor.stue_co2": st("700", device_class="carbon_dioxide"), "binary_sensor.stue_motion": st("on", device_class="motion"),
            "binary_sensor.stue_vindue": st("off", device_class="door"), "binary_sensor.udestue_dor": st("off", device_class="door"),
            "binary_sensor.entre_dor": st("off", device_class="door"), "sensor.bad_hum": st("60", device_class="humidity"),
            "person.anna": st("home", device_trackers=["device_tracker.p"], friendly_name="Anna"),
            "weather.home": st("sunny", temperature=4.0), "sun.sun": st("above_horizon", elevation=20),
            "sensor.vent_ude": st("4", device_class="temperature"), "sensor.vent_indblaes": st("18", device_class="temperature"),
            "sensor.vent_udsug": st("21", device_class="temperature"), "select.vent_ventilatorindstilling": st("2", options=["0", "1", "2", "3", "4"]),
            "sensor.kam_temperature_1_supply": st("60", device_class="temperature"), "sensor.kam_temperature_2_return": st("35", device_class="temperature"),
            "sensor.kam_volume": st("100", unit_of_measurement="m³"),
        }

    async def command(self, msg):
        t = msg["type"]
        if t == "config/area_registry/list":
            return [{"area_id": "stue", "name": "Stue", "floor_id": "f0"}, {"area_id": "bad", "name": "Badeværelse", "floor_id": "f0"}]
        if t == "config/floor_registry/list":
            return [{"floor_id": "f0", "name": "Stueetage", "level": None}]
        if t == "config/device_registry/list":
            return [{"id": "vent", "manufacturer": "Dantherm"}, {"id": "kam", "manufacturer": "Kamstrup"}]
        if t == "config/entity_registry/list":
            area = {"climate.stue": "stue", "sensor.stue_temp": "stue", "sensor.stue_hum": "stue", "sensor.stue_co2": "stue",
                    "binary_sensor.stue_motion": "stue", "binary_sensor.stue_vindue": "stue", "climate.bad": "bad", "sensor.bad_hum": "bad"}
            out = [{"entity_id": e, "area_id": area.get(e), "platform": "mqtt"} for e in self.states]
            for e in out:
                if e["entity_id"].startswith(("sensor.vent", "select.vent")):
                    e.update(device_id="vent", platform="dantherm")
                if e["entity_id"].startswith("sensor.kam"):
                    e["device_id"] = "kam"
            return out
        if t == "get_services":
            return {"notify": {"mobile_app_anna": {}}}
        return []

    async def history(self, *a):
        return [[]]

    async def call_service(self, *a, **k):
        return {}

    async def set_state(self, *a):
        pass


def test_a_whole_round(tmp_path):
    p = Pilot(FakeHA(), tmp_path)
    asyncio.run(p.discover())
    p.set_room("stue", {"evening": 22.0, "doors_extra": ["binary_sensor.udestue_dor"]})
    for _ in range(3):
        p.tick()
    s = p.status()
    names = {r["name"]: r for r in s["rooms"]}
    assert set(names) == {"Stue", "Badeværelse"}
    assert names["Stue"]["windows"] == ["binary_sensor.stue_vindue"] and "binary_sensor.udestue_dor" in names["Stue"]["doors"]
    assert names["Stue"]["want"]["temp"] is not None
    assert s["vent"]["level"] in ("low", "normal", "high", "boost") and s["cooling_now"]["now"] == 25.0
    assert s["persons"][0]["home"] and s["arm"] in ("normal", "early", "gentle")
    assert p.sentence()


def test_shadow_sends_nothing_control_sends_once(tmp_path):
    ha = FakeHA()
    sent = []

    async def call_service(domain, service, data, **k):
        sent.append((domain, service, data))
        ha.states[data["entity_id"]]["attributes"]["temperature"] = data.get("temperature", ha.states[data["entity_id"]]["attributes"].get("temperature"))

    ha.call_service = call_service
    p = Pilot(ha, tmp_path)
    asyncio.run(p.discover())
    p.tick()
    asyncio.run(p.control())
    assert sent == []  # every room starts in shadow
    p.set_mode("stue", "control")
    p.settings["rooms"] = {"stue": {"comfort": 23.0}}
    p.tick()
    asyncio.run(p.control())
    temps = [d for _d, s, d in sent if s == "set_temperature"]
    assert temps and temps[0]["entity_id"] == "climate.stue"
    n = len(sent)
    p.tick()
    asyncio.run(p.control())
    assert len(sent) == n  # nothing new to send: nothing sent
    p.set_mode(None, "shadow")
    assert p.mode("stue") == "shadow"


def test_fahrenheit_home(tmp_path):
    ha = FakeHA()
    ha.config = {"time_zone": "America/New_York", "unit_system": {"temperature": "°F"}}
    for e in ("climate.stue",):
        ha.states[e]["attributes"].update(temperature=70, current_temperature=69, min_temp=41, max_temp=86, target_temp_step=1)
    ha.states["sensor.stue_temp"] = {"state": "69.8", "attributes": {"device_class": "temperature", "unit_of_measurement": "°F"}, "last_changed": NOW.isoformat()}
    p = Pilot(ha, tmp_path)
    asyncio.run(p.discover())
    p.tick()
    r = {x["name"]: x for x in p.status()["rooms"]}["Stue"]
    assert abs(r["temp"] - 21.0) < 0.1  # 69.8 °F = 21 °C inside
    t = [c for c in r["calls"] if c["service"] == "set_temperature"][0]["data"]["temperature"]
    assert t > 60  # sent in °F
