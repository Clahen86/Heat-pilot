"""District heating cooling and electric heating by price."""

from datetime import datetime, timedelta, timezone

from heat_pilot import plan, supply

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def s(v, cls=None, unit=None, name=""):
    return {"state": str(v), "attributes": {"device_class": cls, "unit_of_measurement": unit, "friendly_name": name}}


def test_heat_meter_found_and_not_a_ventilation_unit():
    ents = [{"entity_id": "sensor.kamst_temperature_1_supply", "device_id": "m"}, {"entity_id": "sensor.kamst_temperature_2_return", "device_id": "m"},
            {"entity_id": "sensor.kamst_volume", "device_id": "m"}, {"entity_id": "sensor.kamst_flow_rate", "device_id": "m"},
            {"entity_id": "sensor.vent_supply_temperature", "device_id": "v"}, {"entity_id": "sensor.vent_outdoor", "device_id": "v"}]
    st = {"sensor.kamst_temperature_1_supply": s(62, "temperature"), "sensor.kamst_temperature_2_return": s(35, "temperature"),
          "sensor.kamst_volume": s(11000, None, "m³"), "sensor.kamst_flow_rate": s(0.2, None, "m³/h"),
          "sensor.vent_supply_temperature": s(19, "temperature"), "sensor.vent_outdoor": s(5, "temperature")}
    m = supply.find_heat_meter(ents, [{"id": "m", "manufacturer": "Kamstrup"}, {"id": "v"}], st)
    assert m["supply"] == "sensor.kamst_temperature_1_supply" and m["return"] == "sensor.kamst_temperature_2_return"
    assert m["volume"] == "sensor.kamst_volume"


def test_cooling_weighted_by_water():
    state = {}
    c = supply.Cooling(state)
    meter = {"supply": "s", "return": "r", "volume": "v"}
    c.see(meter, {"s": s(60), "r": s(40), "v": s(100.0)}, NOW)           # first: no weight yet
    c.see(meter, {"s": s(60), "r": s(40), "v": s(101.0)}, NOW)           # 1 m3 at 20 °C
    c.see(meter, {"s": s(60), "r": s(30), "v": s(104.0)}, NOW)           # 3 m3 at 30 °C
    info = c.summary(NOW, 25.0, 5.0, 2.5)
    assert info["today"] == 27.5 and info["year"] == 27.5
    assert info["per_mwh"] == 6.25  # 2.5 °C better than needed x 2.5 kr bonus
    assert not supply.poor_cooling(info, 25.0) and supply.poor_cooling({"today": 20.0}, 25.0)


def test_spread_heats_gently_when_cooling_is_poor():
    room = {"kind": "living", "windows": []}
    at = NOW.replace(hour=16, minute=20)
    assert plan.target(room, {}, {}, at, False, None, [17], 18.0, 12.0)["why"] == "setback"  # 36 min lead: too early
    w = plan.target(room, {}, {}, at, False, None, [17], 18.0, 12.0, spread=True)  # 54 min lead: starts, gently
    assert w["why"] == "spread" and w["temp"] == 18.5


def test_price_levels_and_electric_rooms():
    prices = {NOW.replace(minute=0) + timedelta(hours=h): p for h, p in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])}
    assert supply.price_level(prices, NOW) == "cheap"
    assert supply.price_level(prices, NOW + timedelta(hours=11)) is None  # too little ahead to judge
    room = {"kind": "living", "windows": []}
    assert plan.target(room, {}, {}, NOW, False, None, price="cheap") == {"temp": 22.0, "why": "cheap", "until": NOW.replace(hour=22).isoformat()}
    assert plan.target(room, {}, {}, NOW, False, None, price="dear")["temp"] == 20.0
    assert supply.is_electric({"heating": "heatpump"}) and supply.is_electric({"thermostats": [{"platform": "melcloud"}]})
    assert not supply.is_electric({"heating": "radiator", "thermostats": [{"platform": "mqtt"}]})
