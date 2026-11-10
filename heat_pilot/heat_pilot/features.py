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
