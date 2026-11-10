"""The extras: each turns itself on when what it needs is found in the house, can be turned off, and is not shown
at all when it isn't there."""

from __future__ import annotations

from typing import Any

# key: (what it needs, on by default)
FEATURES = ["signals", "shower", "sun", "weather", "door", "manual", "people", "holiday", "summer", "district", "price", "ventilation"]


def found(rooms: list[dict[str, Any]], states: dict[str, Any], doors: list[str], persons: list[str] | None = None,
          meter: dict | None = None, price: str | None = None, vent: dict | None = None) -> dict[str, bool]:
    from .supply import is_electric

    return {
        "signals": any(r.get("co2") or r.get("humidity") or r.get("lights") for r in rooms),
        "shower": any(r.get("kind") == "bathroom" and r.get("humidity") for r in rooms),
        "sun": "sun.sun" in states and any(e.startswith("weather.") for e in states),
        "weather": any(e.startswith("weather.") for e in states),
        "door": bool(doors) and any(r.get("presence") for r in rooms),
        "manual": any(r.get("thermostats") for r in rooms),
        "people": bool(persons),
        "holiday": bool(persons) or any(e.startswith("calendar.") for e in states),
        "summer": any(e.startswith("weather.") for e in states),
        "district": bool(meter),
        "ventilation": bool(vent),
        "price": bool(price) and any(is_electric(r) for r in rooms),
    }


def active(settings: dict[str, Any], have: dict[str, bool]) -> dict[str, bool]:
    chosen = settings.get("features") or {}
    return {k: bool(have.get(k)) and chosen.get(k, True) is not False for k in FEATURES}


# What can be adjusted, and the easy choices for it: key -> (module, constant, default, choices, unit, feature or None).
TUNE: dict[str, tuple[str, str, float, list[float], str, str | None]] = {
    "window_min": ("plan", "WINDOW_MIN", 5, [2, 5, 10, 15], "min", None),
    "away_temp": ("plan", "AWAY", 17, [15, 16, 17, 18, 19], "°", None),
    "shower_min": ("signals", "SHOWER_MIN", 60, [30, 60, 90], "min", "shower"),
    "door_min": ("signals", "DOOR_AWAY_MIN", 10, [5, 10, 20, 30], "min", "door"),
    "manual_min": ("signals", "MANUAL_MIN", 60, [30, 60, 120, 240], "min", "manual"),
    "near_km": ("people", "NEAR_KM", 15, [5, 15, 30], "km", "people"),
    "holiday_temp": ("plan", "HOLIDAY", 15, [12, 14, 15, 16, 17], "°", "holiday"),
    "holiday_after": ("people", "HOLIDAY_AFTER_H", 24, [12, 24, 48], "h", "holiday"),
    "summer_c": ("people", "SUMMER_C", 16, [14, 15, 16, 17, 18, 20], "°", "summer"),
    "price_flex": ("plan", "PRICE_FLEX", 1.0, [0.5, 1.0, 1.5, 2.0], "°", "price"),
    "co2_high": ("ventilation", "CO2_HIGH", 1000, [800, 1000, 1200], "ppm", "ventilation"),
    "hum_high": ("ventilation", "HUM_HIGH", 65, [55, 60, 65, 70], "%", "ventilation"),
}


def apply_tune(settings: dict[str, Any]) -> None:
    """The user's choices into the modules (one process: the constants are the settings)."""
    import importlib

    own = settings.get("tune") or {}
    for key, (mod, const, default, choices, _unit, _f) in TUNE.items():
        v = own.get(key, default)
        setattr(importlib.import_module(f"heat_pilot.{mod}"), const, v if v in choices else default)


def tune_view(settings: dict[str, Any]) -> dict[str, Any]:
    own = settings.get("tune") or {}
    return {k: {"value": own.get(k, d), "choices": c, "unit": u, "feature": f} for k, (_m, _c, d, c, u, f) in TUNE.items()}
