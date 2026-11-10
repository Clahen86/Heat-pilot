"""What each room should be now - and why. Shadow first: this is only worked out and shown.

The order, highest first:
1. A window or door open for a few minutes: heating off (no heating the garden).
2. Someone turned the thermostat: their temperature, for a while.
3. Everyone away (no movement in the house for an hour, daytime): at most the away temperature.
4. Night: the night temperature. Day: the room's comfort temperature in its hours, else the setback.
Always within the frost guard and the room's own limits.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# Starting points by kind of room - changed by the user, later learned.
COMFORT = {"living": 21.0, "kitchen": 20.0, "bedroom": 19.0, "kids": 20.0, "bathroom": 22.0, "office": 20.5, "other": 20.0}
NIGHT = {"bedroom": 18.0, "bathroom": 19.0}
DAY_HOURS = {"living": (6, 22), "kitchen": (6, 22), "bedroom": (6, 8), "kids": (6, 21), "bathroom": (5, 22),
             "office": (7, 18), "other": (6, 22)}
SETBACK = 18.0
AWAY = 17.0
FROST = 7.0
WINDOW_MIN = 5
AWAY_MIN = 60
MANUAL_MIN = 60


def defaults(room: dict[str, Any]) -> dict[str, Any]:
    kind = room.get("kind") or "other"
    start, end = DAY_HOURS.get(kind, (6, 22))
    return {"comfort": COMFORT.get(kind, 20.0), "setback": SETBACK, "night": NIGHT.get(kind, SETBACK),
            "day_from": start, "day_to": end, "away": AWAY}


def _minutes_open(states: dict[str, Any], entity: str, now: datetime) -> float | None:
    s = states.get(entity) or {}
    if s.get("state") != "on":
        return None
    try:
        since = datetime.fromisoformat(s["last_changed"])
    except (KeyError, ValueError, TypeError):
        return 0.0
    return (now - since).total_seconds() / 60


def target(room: dict[str, Any], cfg: dict[str, Any], states: dict[str, Any], now: datetime,
           house_away: bool, manual: dict[str, Any] | None) -> dict[str, Any]:
    """{"temp": °C or None (off), "why": key, "until": time the reason ends or None}."""
    c = {**defaults(room), **(cfg or {})}
    for w in room.get("windows") or []:
        m = _minutes_open(states, w, now)
        if m is not None and m >= WINDOW_MIN:
            return {"temp": None, "why": "window", "entity": w}
    if manual and manual.get("until") and now < manual["until"]:
        return {"temp": manual["temp"], "why": "manual", "until": manual["until"].isoformat()}
    h = now.hour + now.minute / 60
    day = c["day_from"] <= h < c["day_to"]
    if day:
        t, why = c["comfort"], "comfort"
        until = now.replace(hour=int(c["day_to"]) % 24, minute=0, second=0, microsecond=0)
    else:
        t, why = (c["night"], "night") if (h >= 21 or h < 6) else (c["setback"], "setback")
        nxt = now.replace(hour=int(c["day_from"]), minute=0, second=0, microsecond=0)
        until = nxt if nxt > now else nxt + timedelta(days=1)
    if house_away and 6 <= now.hour < 23 and t > c["away"]:
        t, why, until = c["away"], "away", None
    return {"temp": max(FROST, round(t, 1)), "why": why, "until": until.isoformat() if until else None}


def house_away(rooms: list[dict[str, Any]], states: dict[str, Any], now: datetime, last_motion: datetime | None) -> bool:
    """Nobody seen anywhere for an hour (only rooms with motion sensors count)."""
    sensors = [p for r in rooms for p in r.get("presence") or []]
    if not sensors:
        return False
    if any((states.get(p) or {}).get("state") == "on" for p in sensors):
        return False
    latest = last_motion
    for p in sensors:
        try:
            t = datetime.fromisoformat((states.get(p) or {})["last_changed"])
        except (KeyError, ValueError, TypeError):
            continue
        latest = t if latest is None or t > latest else latest
    return latest is not None and (now - latest).total_seconds() >= AWAY_MIN * 60
