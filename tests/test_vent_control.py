"""Heat Pilot running the ventilation: only what isn't so already, the unit in manual first, and back to automatic."""

from datetime import datetime

from heat_pilot import air, ventilation

UNIT = {"level_select": "select.fan", "mode_select": "select.drift", "fan": None}


def st(fan="1", drift="automatic"):
    return {"select.fan": {"state": fan, "attributes": {"options": ["0", "1", "2", "3", "4"]}},
            "select.drift": {"state": drift, "attributes": {"options": ["standby", "automatic", "manual", "fireplace"]}}}


def test_calls_put_the_unit_in_manual_then_the_step():
    c = ventilation.calls(UNIT, st("1", "automatic"), "boost")
    assert [x["data"]["option"] for x in c] == ["manual", "4"]
    assert ventilation.calls(UNIT, st("4", "manual"), "boost") == []      # already so: nothing sent


def test_handback_and_pause_modes():
    assert ventilation.handback_calls(UNIT, st())[0]["data"]["option"] == "automatic"
    assert "fireplace" in ventilation.PAUSE_MODES and ventilation.mode_now(UNIT, st(drift="fireplace")) == "fireplace"


def test_step_now():
    assert ventilation.current_step(UNIT, st("3")) == (3, 4)


def test_precool_before_a_warm_day():
    w = air.AirWatch()
    room = {"area_id": "sov", "name": "Soveværelse", "kind": "bedroom", "humidity": [], "co2": []}
    night = datetime(2026, 7, 1, 23, 30)
    out = air.decide([room], {}, w, night, away=False, house_temp=22.0, comfort=21.0, outdoor=15.0, outdoor_dp=10.0, tomorrow_max=28.0)
    assert out["why"] == "precool" and out["cooling"]
    cool_day = air.decide([room], {}, w, night, away=False, house_temp=22.0, comfort=21.0, outdoor=15.0, outdoor_dp=10.0, tomorrow_max=18.0)
    assert cool_day["why"] != "precool"
