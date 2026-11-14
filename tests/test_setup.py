"""The setup sent to the developer: names without the user's own names, the full names only when shared."""

from types import SimpleNamespace

from heat_pilot import setup
from heat_pilot.support import Support

REGS = {"climate.stue_termostat": {"entity_id": "climate.stue_termostat", "platform": "zha", "device_id": "d1"},
        "climate.lillys_rum": {"entity_id": "climate.lillys_rum", "platform": "mqtt", "device_id": "d2", "translation_key": None},
        "sensor.vvb_temp": {"entity_id": "sensor.vvb_temp", "platform": "esphome", "device_id": "d3", "translation_key": "tank_temperature"}}
DEVS = {"d1": {"id": "d1", "name": "Stue termostat", "manufacturer": "Aqara", "model": "E1"},
        "d2": {"id": "d2", "name": "TRV", "name_by_user": "Radiator"},
        "d3": {"id": "d3", "name": "Boiler"}}


def test_mask():
    words = setup.personal_words({"person.lilly": {"attributes": {"friendly_name": "Lilly"}}}, {"location_name": "Hjem"}, {}, ["Stue", "Køkken"])
    assert setup.mask("climate.stue_termostat", REGS, DEVS, words) == "climate.<device>"
    assert setup.mask("climate.lillys_rum", REGS, DEVS, words) == "climate.<person>_rum"  # Lilly's room
    assert setup.mask("climate.stue_radiator", REGS, DEVS, words) == "climate.stue_radiator"  # rooms stay
    assert setup.mask("sensor.vvb_temp", REGS, DEVS, words) == "sensor.vvb_temp"  # nothing personal: the whole name


class Pilot:
    def __init__(self):
        self.ha = SimpleNamespace(states={"climate.stue_termostat": {"state": "heat", "attributes": {
            "hvac_modes": ["off", "heat"], "preset_modes": ["away", "none"], "min_temp": 5, "max_temp": 30, "friendly_name": "Stue"}}})
        self.reg_entities, self.reg_devices = REGS, DEVS
        self.settings = {"support": {"install": "a" * 32}}
        self.sender = SimpleNamespace(log=[{"call": "climate.set_temperature", "data": {"entity_id": "climate.stue_termostat"}, "ok": False}])
        self.watchdog = SimpleNamespace(lost={})
        self.on = {"sun": True, "price": False}
        self.agree = {"same": 9, "checks": 10}
        self.vent = self.meter = self.price_entity = None

    def rooms(self):
        return [{"area_id": "stue", "name": "Stue", "heating": "radiator", "thermostats": [
            {"entity_id": "climate.stue_termostat", "platform": "zha", "brand": "Aqara", "manufacturer": "Aqara", "model": "E1"}]}]

    def mode(self, _a):
        return "control"

    def save(self):
        pass


def test_collect_and_no_room_names():
    p = Pilot()
    su = setup.collect(p, full=False)
    th = su["devices"][0]
    assert th["kind"] == "thermostat" and th["profile"] == "Aqara" and th["ok"] is False
    assert th["entities"][0]["name"] == "climate.<device>" and th["entities"][0]["hvac_modes"] == ["off", "heat"]
    assert "friendly_name" not in str(su) and "Stue" not in str(su).replace("Stue termostat", "")
    assert su["sizes"]["rooms"] == "1-3" and su["counts"] == {"rooms_controlled": 1, "agree_pct": 90}
    assert su["features"] == {"sun": True, "price": False}


def test_only_when_shared_and_full_when_chosen():
    p = Pilot()
    s = Support(p)
    assert s.setup_info()["full"] is False
    s.d["full"] = True
    assert s.setup_info()["devices"][0]["entities"][0]["name"] == "climate.stue_termostat"
    s.d["share"] = False
    assert s.setup_info() is None and s.full is False
