"""What each room should be now - and why. Shadow first: this is only worked out and shown.

The order, highest first:
1. A window or door open for a few minutes: heating off (no heating the garden).
2. Someone turned the thermostat: their temperature, for a while.
3. Everyone away (no movement in the house for an hour, daytime): at most the away temperature.
4. Comfort in the room's hours (learned from when it is used, or as set) - and heating started in time before them,
   from the learned minutes per degree. Otherwise the setback, and at night the night temperature.
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
HOLIDAY = 15.0
PRICE_FLEX = 1.0  # degrees up in the cheapest hours / down in the dearest (electric heating)
FROST = 7.0
WINDOW_MIN = 5
AWAY_MIN = 60
MANUAL_MIN = 60


def defaults(room: dict[str, Any]) -> dict[str, Any]:
    kind = room.get("kind") or "other"
    start, end = DAY_HOURS.get(kind, (6, 22))
    return {"comfort": COMFORT.get(kind, 20.0), "setback": SETBACK, "night": NIGHT.get(kind, SETBACK),
            "day_from": start, "day_to": end, "away": AWAY, "holiday": HOLIDAY}


def _minutes_open(states: dict[str, Any], entity: str, now: datetime) -> float | None:
    s = states.get(entity) or {}
    if s.get("state") != "on":
        return None
    try:
        since = datetime.fromisoformat(s["last_changed"])
    except (KeyError, ValueError, TypeError):
        return 0.0
    return (now - since).total_seconds() / 60


def comfort_at(c: dict[str, Any], hours: list[int] | None, t: datetime) -> bool:
    """A comfort hour: learned when it is, else the room's own hours."""
    if hours is not None:
        return t.hour in hours
    h = t.hour + t.minute / 60
    return c["day_from"] <= h < c["day_to"]


def base(c: dict[str, Any], hours: list[int] | None, t: datetime) -> tuple[float, str]:
    if comfort_at(c, hours, t):
        ev = c.get("evening")
        if ev is not None and c.get("evening_from", 15) <= t.hour < c.get("evening_to", 22):
            return float(ev), "evening"  # a warmer (or cooler) evening, e.g. the living room at 22° from 15 to 22
        return c["comfort"], "comfort"
    h = t.hour + t.minute / 60
    return (c["night"], "night") if (h >= 22 or h < 6) else (c["setback"], "setback")


def next_comfort(c: dict[str, Any], hours: list[int] | None, now: datetime, within_h: int = 8) -> datetime | None:
    t = now.replace(minute=0, second=0, microsecond=0)
    for _ in range(within_h * 4):
        t += timedelta(minutes=15)
        if comfort_at(c, hours, t):
            return t
    return None


def target(room: dict[str, Any], cfg: dict[str, Any], states: dict[str, Any], now: datetime,
           house_away: bool, manual: dict[str, Any] | None, hours: list[int] | None = None,
           temp: float | None = None, rate: float | None = None, occupied: bool = False, shower: bool = False,
           sun: bool = False, summer: bool = False, holiday: str | None = None, owner_away: bool = False,
           coming: bool = False, price: str | None = None, spread: bool = False, cooling: bool = False,
           extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"temp": °C or None (off), "why": key, "until": time the reason ends or None}.

    extra (all optional, from what was learned and seen): door (a door in the room open a while), noshow (nobody in
    the room today, afternoon), sun_ahead (°C the sun will give before comfort), arm (today's strategy), cold_snap,
    floor_active (someone on the same floor - floor heating), buffer (district cooling poor - floors take heat),
    hold_warm (the gap to the next comfort is too short for setting back to pay)."""
    x = extra or {}
    c = {**defaults(room), **(cfg or {})}
    for w in room.get("windows") or []:
        m = _minutes_open(states, w, now)
        if m is not None and m >= WINDOW_MIN:
            return {"temp": None, "why": "window", "entity": w}
    if summer:
        return {"temp": None, "why": "summer"}
    if cooling and not shower:
        return {"temp": None, "why": "cooling"}  # the ventilation (or another system) cools the house: never heat against it
    if manual and manual.get("until") and now < manual["until"]:
        return {"temp": manual["temp"], "why": "manual", "until": manual["until"].isoformat()}
    t, why = base(c, hours, now)
    if why == "evening":
        why = "comfort_evening"
    if x.get("floor_active") and room.get("heating") == "floor" and 6 <= now.hour < 22 and c["comfort"] > t:
        t, why = c["comfort"], "floor"  # floor heating is slow: warm while someone is on the same floor
    if x.get("hold_warm") and why in ("setback",) and c["comfort"] > t:
        t, why = c["comfort"], "hold"  # a short gap: setting back wouldn't pay (it hardly cools)
    if shower and c["comfort"] > t:
        t, why = c["comfort"], "shower"  # warm during and after the shower
    elif occupied and why != "comfort" and 6 <= now.hour < 22 and c["comfort"] > t:
        t, why = c["comfort"], "occupied"  # someone is in the room now: comfort, whatever the plan said
    until = None
    if why in ("comfort", "comfort_evening"):
        e = now.replace(second=0, microsecond=0)
        while comfort_at(c, hours, e) and e < now + timedelta(hours=24):
            e += timedelta(minutes=15)
        until = e
    elif why not in ("occupied", "shower"):
        nxt = next_comfort(c, hours, now)
        if nxt is not None:
            until = nxt
            # Start in time: warm when the room is used - the learned minutes per degree from where it is now.
            if temp is not None and rate:
                lead = max(0.0, c["comfort"] - temp) * rate
                gentle = spread or x.get("arm") == "gentle"
                if gentle:
                    lead *= 1.5  # district cooling poor (or today's strategy): start earlier, warm gently
                if x.get("arm") == "early":
                    lead *= 1.4
                if x.get("cold_snap"):
                    lead *= 1.3  # much colder weather coming: start earlier
                if x.get("noshow"):
                    lead = 0  # nobody has been in the room today: warm it when someone comes
                if x.get("sun_ahead", 0) >= max(0.3, (c["comfort"] - temp) * 0.6):
                    sun = True  # the sun will do most of it before the room is used
                if now >= nxt - timedelta(minutes=lead) and c["comfort"] > t:
                    if sun:
                        t, why = t, "sun"  # the sun warms it for free
                    elif gentle:
                        t, why = min(c["comfort"], temp + 0.5), "spread"  # a little at a time: low return temperature
                    else:
                        t, why = c["comfort"], "preheat"
    if x.get("door") and t is not None and why not in ("shower",):
        t, why = t - 2.0, "door"  # a door open to the outside or a cold room: a little lower, not off
    if x.get("buffer") and room.get("heating") == "floor" and why not in ("setback", "night"):
        t, why = min(c["comfort"] + 1.0, 23.0), "buffer"  # floors take the heat: lower district return temperature
    # Electric heating / heat pump: warmer in the cheapest hours (heat stored in the house), cooler in the dearest.
    flex = float(c.get("price_flex", PRICE_FLEX))
    if price == "cheap" and why in ("comfort", "comfort_evening", "occupied", "preheat", "setback"):
        t, why = t + flex, "cheap"
    elif price == "dear" and why in ("comfort", "comfort_evening", "occupied"):
        t, why = t - flex, "dear"
    if holiday and not coming:
        return {"temp": max(FROST, c.get("holiday", HOLIDAY)), "why": "holiday", "kind": holiday}
    if owner_away and why not in ("shower",) and t > c["setback"]:
        t, why, until = c["setback"], "owner_away", None
    if house_away and not coming and t > c["away"]:
        t, why, until = c["away"], "away", None
    return {"temp": max(FROST, round(t, 1)), "why": why, "until": until.isoformat() if until else None}


def timeline(room: dict[str, Any], cfg: dict[str, Any], now: datetime, hours_by_day: dict[int, list[int] | None],
             temp: float | None, rate: float | None, steps: int = 96) -> list[dict[str, Any]]:
    """The next 24 hours in quarters: the temperature and why - with heating started in time before comfort."""
    c = {**defaults(room), **(cfg or {})}
    t0 = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
    out = []
    for i in range(steps):
        t = t0 + timedelta(minutes=15 * i)
        v, why = base(c, hours_by_day.get(t.weekday()), t)
        out.append({"t": t.isoformat(), "temp": v, "why": "comfort" if why == "evening" else why})
    lead_q = int(round(max(0.0, c["comfort"] - (temp if temp is not None else c["setback"])) * (rate or 12) / 15)) if rate else 0
    lead_q = max(lead_q, 1)
    for i in range(len(out)):
        if out[i]["why"] == "comfort" and i > 0 and out[i - 1]["why"] != "comfort":
            for j in range(max(0, i - lead_q), i):
                if out[j]["why"] != "comfort":
                    out[j] = {**out[j], "temp": c["comfort"], "why": "preheat"}
    return out


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
