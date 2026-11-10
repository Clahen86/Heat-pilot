"""Ventilation: found across brands, what it wants, and the heating keeping out of its way."""

from datetime import datetime, timezone

from heat_pilot import plan, ventilation as v

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def t(x, cls="temperature", name=""):
    return {"state": str(x), "attributes": {"device_class": cls, "friendly_name": name}}


def test_found_with_select_levels_and_bypass():
    ents = [{"entity_id": e, "device_id": "d", "platform": "dantherm"} for e in
            ("sensor.d_udeluftstemperatur", "sensor.d_indblaesningstemperatur", "sensor.d_udsugningstemperatur",
             "sensor.d_udblaesningstemperatur", "select.d_ventilatorindstilling", "select.d_boost_tilstand_indstilling",
             "fan.d_ventilation", "cover.d_bypass_spjaeld")]
    st = {"sensor.d_udeluftstemperatur": t(8), "sensor.d_indblaesningstemperatur": t(18.8), "sensor.d_udsugningstemperatur": t(21.5),
          "sensor.d_udblaesningstemperatur": t(10.7), "select.d_ventilatorindstilling": {"state": "3", "attributes": {"options": ["0", "1", "2", "3", "4"]}},
          "select.d_boost_tilstand_indstilling": {"state": "level_4", "attributes": {"options": ["level_2", "level_3", "level_4"]}},
          "fan.d_ventilation": {"state": "on", "attributes": {}}, "cover.d_bypass_spjaeld": {"state": "closed", "attributes": {}}}
    u = v.find(ents, [{"id": "d", "name": "Dantherm"}], st)
    assert u["level_select"] == "select.d_ventilatorindstilling" and u["bypass"] == "cover.d_bypass_spjaeld"
    assert v.efficiency(u, st) == 80 and v.bypass_open(u, st) is False
    assert v.current_level(u, st) == "high"
    assert [v.level_value(u, st, l) for l in v.LEVELS] == ["1", "2", "3", "4"]  # never 0 (off)


def test_fan_percentage_unit():
    ents = [{"entity_id": e, "device_id": "z", "platform": "comfoconnect"} for e in ("sensor.z_outdoor_temperature", "sensor.z_supply_temperature", "fan.z")]
    st = {"sensor.z_outdoor_temperature": t(5), "sensor.z_supply_temperature": t(18), "fan.z": {"state": "on", "attributes": {"percentage": 40}}}
    u = v.find(ents, [], st)
    assert u["fan"] == "fan.z" and v.current_level(u, st) == "normal"
    assert v.calls(u, st, "boost") == [{"domain": "fan", "service": "set_percentage", "data": {"entity_id": "fan.z", "percentage": 100}}]


def test_not_a_ventilation_unit():
    ents = [{"entity_id": "sensor.boiler_supply_temperature", "device_id": "b"}, {"entity_id": "sensor.boiler_return_temperature", "device_id": "b"}]
    st = {"sensor.boiler_supply_temperature": t(60), "sensor.boiler_return_temperature": t(40)}
    assert v.find(ents, [], st) is None  # no fan control


def test_decide():
    rooms = [{"kind": "living", "co2": ["sensor.c"], "humidity": ["sensor.h"]}]
    st = {"sensor.c": {"state": "700"}, "sensor.h": {"state": "45"}}
    assert v.decide(rooms, st, True, False, 21, 21, 5)["why"] == "shower"
    assert v.decide(rooms, {**st, "sensor.c": {"state": "1200"}}, False, False, 21, 21, 5)["level"] == "high"
    assert v.decide(rooms, {**st, "sensor.c": {"state": "1500"}}, False, False, 21, 21, 5)["level"] == "boost"
    assert v.decide(rooms, st, False, False, 24, 21, 15)["why"] == "free_cooling"
    assert v.decide(rooms, st, False, False, 24, 21, 5)["why"] == "normal"  # too cold outside to cool with
    assert v.decide(rooms, st, False, True, 21, 21, 5)["level"] == "low"


def test_no_heating_while_cooling_and_other_system():
    room = {"kind": "living", "windows": []}
    assert plan.target(room, {}, {}, NOW, False, None, cooling=True)["why"] == "cooling"
    assert v.other_cooling({"sensor.indeklima": {"state": "ok", "attributes": {"precool": "true"}}}, "sensor.indeklima")
    assert not v.other_cooling({"sensor.indeklima": {"state": "ok", "attributes": {"precool": "false"}}}, "sensor.indeklima")
