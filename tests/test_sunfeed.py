from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from heat_pilot.learning import Model
from heat_pilot.sunfeed import MIN_DAYS, SunFeed, hour_key, pv_from_energy, pv_from_states

TZ = ZoneInfo("Europe/Copenhagen")
NOW = datetime(2026, 11, 11, 10, 0, tzinfo=TZ)


def solcast(day_kwh: dict[int, float]) -> dict:
    hours = [{"period_start": NOW.replace(hour=h).isoformat(), "pv_estimate": v} for h, v in day_kwh.items()]
    return {"sensor.solcast_pv_forecast_forecast_today": {"state": "5", "attributes": {"detailedHourly": hours}}}


def test_solcast_and_open_meteo_hours():
    st = solcast({12: 2.0})
    st["sensor.om_today"] = {"attributes": {"wh_period": {NOW.replace(hour=12).isoformat(): 500}}}
    assert pv_from_states(st)[hour_key(NOW.replace(hour=12))] == 2.5


def test_energy_dashboard_hours():
    fc = {"abc": {"wh_hours": {NOW.replace(hour=11).isoformat(): 1500}}}
    assert pv_from_energy(fc, ["abc"]) == {hour_key(NOW.replace(hour=11)): 1.5}


def test_power_forecast_trusted_after_some_days_else_clouds():
    s: dict = {}
    f = SunFeed(s)
    clouds = {hour_key(NOW.replace(hour=12)): 80.0}
    # day 1: a clear day sets the reference; still too new -> cloud cover is used
    out = f.factors(solcast({12: 4.0}), {}, clouds, {}, NOW)
    assert f.source == "cloud cover" and out[hour_key(NOW.replace(hour=12))] == 0.2
    for d in range(1, MIN_DAYS):
        f.factors(solcast({12: 4.0}), {}, clouds, {}, NOW + timedelta(days=d))
    later = NOW + timedelta(days=MIN_DAYS)
    out = f.factors(solcast({12: 1.0}), {}, clouds, {}, later.replace(hour=10))
    assert f.source == "Solcast / Open-Meteo"
    assert 0.2 < out[hour_key(NOW.replace(hour=12))] < 0.3  # a grey day: a quarter of the clear-day reference


def test_conditions_when_no_cloud_cover():
    f = SunFeed({})
    out = f.factors({}, {}, {}, {1: "sunny", 2: "partlycloudy", 3: "rainy"}, NOW)
    assert out == {1: 1.0, 2: 0.5, 3: 0.0} and f.source == "weather forecast"
    assert f.factors({}, {}, {}, {}, NOW) == {} and f.source is None


def test_sun_gain_follows_the_forecast():
    m = Model({})
    m.s["sun"]["r"] = {"11": 1.0, "12": 1.0}
    start = NOW.replace(hour=11)
    assert m.sun_gain("r", start, 2) == 2.0  # no forecast: a sunny day, as before
    sun = {hour_key(start): 1.0, hour_key(start + timedelta(hours=1)): 0.0}
    assert m.sun_gain("r", start, 2, sun) == 1.0  # clouds from noon
