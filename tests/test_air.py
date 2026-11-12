"""The whole house's air: which room decides, and why."""

from datetime import datetime, timedelta

from heat_pilot import air

T0 = datetime(2026, 11, 12, 14, 0)


def st(**vals):
    return {k: {"state": str(v)} for k, v in vals.items()}


BATH = {"area_id": "bad", "name": "Badeværelse", "kind": "bathroom", "humidity": ["sensor.bad_h"], "co2": []}
BED = {"area_id": "sov", "name": "Soveværelse", "kind": "bedroom", "humidity": ["sensor.sov_h"], "co2": ["sensor.sov_co2"]}
GYM = {"area_id": "gym", "name": "Hobby", "kind": "other", "humidity": ["sensor.gym_h"], "co2": ["sensor.gym_co2"]}


def run(states, watch=None, now=T0, **kw):
    args = dict(away=False, house_temp=21.0, comfort=21.0, outdoor=5.0, outdoor_dp=2.0, own={"gym": {"airflow": "none"}})
    args.update(kw)
    return air.decide([BATH, BED, GYM], states, watch or air.AirWatch(), now, **args)


def test_airflow_guess_and_override():
    assert air.airflow(BATH) == "exhaust" and air.airflow(BED) == "supply"
    assert air.airflow({"name": "Køkken"}) == "exhaust" and air.airflow({"name": "Garage"}) == "none"
    assert air.airflow(BED, {"airflow": "exhaust"}) == "exhaust"


def test_shower_boosts_until_damp_is_back():
    w = air.AirWatch()
    for m in range(0, 60, 5):  # a quiet hour at 55 %
        run(st(**{"sensor.bad_h": 55, "sensor.sov_h": 45, "sensor.sov_co2": 600}), w, T0 + timedelta(minutes=m))
    now = T0 + timedelta(minutes=75)
    out = run(st(**{"sensor.bad_h": 80, "sensor.sov_h": 45, "sensor.sov_co2": 600}), w, now)
    assert out["level"] == "boost" and out["why"] == "shower" and out["lead"]["area_id"] == "bad" and out["lead"]["value"] == 80
    back = run(st(**{"sensor.bad_h": 57, "sensor.sov_h": 45, "sensor.sov_co2": 600}), w, now + timedelta(minutes=10))
    assert back["why"] == "save_heat"  # back near normal: no more boost


def test_co2_counts_only_where_fresh_air_comes_in():
    out = run(st(**{"sensor.bad_h": 55, "sensor.sov_h": 45, "sensor.sov_co2": 1250, "sensor.gym_co2": 1800}))
    assert out["level"] == "boost" and out["why"] == "co2" and out["lead"]["area_id"] == "sov"  # the gym has no vents


def test_co2_below_the_limit_gets_no_middle_level():
    s = st(**{"sensor.bad_h": 55, "sensor.sov_h": 45, "sensor.sov_co2": 1150})
    assert run(s)["level"] == "low" and run(s)["why"] == "save_heat"   # cold outside: keep the heat in
    assert run(s, outdoor=12.0)["level"] == "normal"
    assert run(s, params={"co2_boost": 1100})["level"] == "boost"     # a limit learned elsewhere


def test_damp_not_raised_when_outside_air_is_wetter():
    s = st(**{"sensor.bad_h": 55, "sensor.sov_h": 70, "sensor.sov_co2": 600})
    assert run(s, outdoor_dp=2.0)["why"] == "humidity"
    assert run(s, outdoor_dp=17.0)["why"] == "save_heat"


def test_night_and_away_are_low():
    s = st(**{"sensor.bad_h": 55, "sensor.sov_h": 45, "sensor.sov_co2": 600})
    assert run(s, now=T0.replace(hour=2))["why"] == "night"
    assert run(s, away=True)["level"] == "low"


def test_room_air_colour():
    s = st(**{"sensor.sov_h": 45, "sensor.sov_co2": 1100})
    assert air.room_air(BED, s)["air"] == "warn"
    assert air.room_air(BED, st(**{"sensor.sov_co2": 1300}))["air"] == "bad"
    assert air.room_air(GYM, s, {"airflow": "none"})["air"] is None


def test_dewpoint():
    assert abs(air.dewpoint(21, 50) - 10.2) < .3
