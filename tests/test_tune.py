"""Adjusting: the user's choices reach the planner, only from the offered choices."""

from datetime import datetime, timedelta, timezone

from heat_pilot import features, plan, signals

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def test_choices_apply_and_bad_values_fall_back():
    features.apply_tune({"tune": {"window_min": 15, "away_temp": 19, "shower_min": 999}})
    try:
        assert plan.WINDOW_MIN == 15 and plan.AWAY == 19 and signals.SHOWER_MIN == 60
        s = {"binary_sensor.w": {"state": "on", "last_changed": (NOW - timedelta(minutes=10)).isoformat()}}
        assert plan.target({"kind": "living", "windows": ["binary_sensor.w"]}, {}, s, NOW, False, None)["why"] == "comfort"
        assert plan.target({"kind": "living", "windows": []}, {}, {}, NOW, True, None)["temp"] == 19
    finally:
        features.apply_tune({})
    assert plan.WINDOW_MIN == 5 and plan.AWAY == 17


def test_view_lists_choices():
    v = features.tune_view({"tune": {"price_flex": 2.0}})
    assert v["price_flex"]["value"] == 2.0 and v["price_flex"]["feature"] == "price" and v["window_min"]["feature"] is None
