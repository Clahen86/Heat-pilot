"""Each kind of thermostat is driven its own way - from the integrations' source and the devices' documentation."""

from heat_pilot import brands


def test_profiles_by_model_and_platform():
    assert brands.profile("mqtt", "Smart radiator thermostat E1", "Aqara")["away_is_frost"]
    assert brands.profile("mqtt", "TRVZB", "SONOFF")["room_sensor"][0] == "external_temperature_input"
    assert brands.profile("mqtt", "014G2461", "Danfoss")["no_off"]
    assert brands.profile("netatmo", None, None)["expires_min"] == 120
    assert brands.profile("tado", None, None)["cloud"]
    assert brands.profile("zha", "unknown", "Acme")["name"] == "Acme unknown"


def test_no_off_uses_lowest_setpoint():
    a = {"hvac_modes": ["heat"], "min_temp": 5}
    calls = brands.off_calls("climate.ally", a, brands.profile("mqtt", "014G2461", "Danfoss"))
    assert calls == [{"domain": "climate", "service": "set_temperature", "data": {"entity_id": "climate.ally", "temperature": 5.0}}]
    a = {"hvac_modes": ["off", "heat"]}
    assert brands.off_calls("climate.e1", a, brands.profile("mqtt", "SRTS-A01", "Aqara"))[0]["service"] == "set_hvac_mode"


def test_aqara_heats_in_manual_preset_never_away():
    a = {"hvac_modes": ["off", "heat"], "preset_modes": ["none", "manual", "away", "auto"], "preset_mode": "auto", "_state": "off",
         "target_temp_step": 0.5, "min_temp": 5, "max_temp": 30}
    calls = brands.heat_calls("climate.e1", a, brands.profile("mqtt", "Smart radiator thermostat E1", "Aqara"), 20.3)
    assert [c["service"] for c in calls] == ["set_hvac_mode", "set_preset_mode", "set_temperature"]
    assert calls[1]["data"]["preset_mode"] == "manual" and calls[2]["data"]["temperature"] == 20.5


def test_tuya_regulates_in_auto_not_heat():
    a = {"hvac_modes": ["heat", "auto", "off"], "preset_modes": ["schedule", "manual", "boost"], "preset_mode": "schedule", "_state": "heat"}
    calls = brands.heat_calls("climate.tuya", a, brands.profile("mqtt", "TS0601", "TuYa"), 21)
    assert calls[0]["data"]["hvac_mode"] == "auto" and calls[1]["data"]["preset_mode"] == "manual"


def test_step_and_range():
    assert brands.round_step(21.26, {"target_temp_step": 0.1}) == 21.3
    assert brands.round_step(40, {"max_temp": 28}) == 28
