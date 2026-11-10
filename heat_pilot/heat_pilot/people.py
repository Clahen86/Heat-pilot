"""People and the year: who is home, who is on the way, holidays and summer.

- Everyone away (Home Assistant's persons, from their phones): the house goes to the away temperature - day and
  night - without waiting for motion sensors.
- On the way home: with Home Assistant's Proximity helper, a person heading home and within 15 km ends "away"
  early, so the house is warm when they arrive.
- A room that belongs to someone (found from the name: "Dennis værelse" belongs to person.dennis, or chosen):
  set back while that person is away.
- Holiday: everyone away for more than a day, or a calendar event called holiday/ferie/urlaub/… right now -
  the holiday temperature (frost-safe and cheap).
- Summer: the last three days' average outdoor temperature above 16 °C - heating off until it cools again.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

HOLIDAY_WORDS = re.compile(r"ferie|vacation|holiday|urlaub|semester|vacances|vakantie|bortrejst|ferien", re.I)
NEAR_KM = 15
SUMMER_C = 16.0
HOLIDAY_AFTER_H = 24


def persons(states: dict[str, Any]) -> list[str]:
    """Persons with something that tracks them (a phone, a router …)."""
    return sorted(e for e, s in states.items() if e.startswith("person.")
                  and (s.get("attributes") or {}).get("device_trackers") and s.get("state") not in ("unknown", "unavailable"))


def home(states: dict[str, Any], p: str) -> bool:
    return (states.get(p) or {}).get("state") == "home"


def all_away(states: dict[str, Any], ps: list[str]) -> bool:
    return bool(ps) and not any(home(states, p) for p in ps)


def away_since(states: dict[str, Any], ps: list[str]) -> datetime | None:
    """When the last person left (everyone away)."""
    if not all_away(states, ps):
        return None
    out = None
    for p in ps:
        try:
            t = datetime.fromisoformat((states.get(p) or {})["last_changed"])
        except (KeyError, ValueError, TypeError):
            continue
        out = t if out is None or t > out else out
    return out


def _slug(p: str) -> str:
    return p.split(".", 1)[1]


def coming_home(states: dict[str, Any], ps: list[str]) -> list[str]:
    """Persons heading home and close (Proximity helper: …_<person>_distance + …_direction_of_travel)."""
    out = []
    for p in ps:
        if home(states, p):
            continue
        slug = _slug(p)
        for e, s in states.items():
            if not (e.startswith("sensor.") and e.endswith(f"_{slug}_direction_of_travel")):
                continue
            if s.get("state") != "towards":
                continue
            dist_e = e[: -len("direction_of_travel")] + "distance"
            d = states.get(dist_e) or {}
            try:
                km = float(d.get("state"))
            except (TypeError, ValueError):
                continue
            unit = str((d.get("attributes") or {}).get("unit_of_measurement") or "km").lower()
            km = km / 1000 if unit == "m" else km * 1.609 if unit == "mi" else km
            if km <= NEAR_KM:
                out.append(p)
    return out


def owner_of(room_name: str, ps: list[str], states: dict[str, Any]) -> str | None:
    """The person a room is named after (first name in the room's name). A shared room ("Holly & Lilly") only gets
    an owner when everyone in its name is a person - else it can't be known that the room is empty."""
    words = set(re.findall(r"[a-zæøåäöü]+", room_name.lower()))
    found = []
    for p in ps:
        first = str((states.get(p) or {}).get("attributes", {}).get("friendly_name") or _slug(p)).split()[0].lower()
        if first in words or _slug(p).split("_")[0] in words:
            found.append(p)
    shared = bool(re.search(r"&|\+|/|\bog\b|\band\b|\bund\b|\boch\b|\ben\b|\bet\b", room_name.lower()))
    if not found or (shared and len(found) < 2):
        return None
    return ",".join(found)


def owners_away(states: dict[str, Any], owner: str | None) -> bool:
    """Everyone the room belongs to is away."""
    ps = [p for p in (owner or "").split(",") if p]
    return bool(ps) and not any(home(states, p) for p in ps)


def holiday_event(states: dict[str, Any]) -> str | None:
    """A calendar event called holiday/ferie/… going on now."""
    for e, s in states.items():
        if e.startswith("calendar.") and s.get("state") == "on":
            msg = str((s.get("attributes") or {}).get("message") or "")
            if HOLIDAY_WORDS.search(msg):
                return msg
    return None


def holiday(states: dict[str, Any], ps: list[str], now: datetime, use_calendar: bool) -> str | None:
    """Why the house is on holiday: "calendar", "away_long" - or None."""
    if use_calendar and holiday_event(states):
        return "calendar"
    since = away_since(states, ps)
    if since is not None and (now - since) >= timedelta(hours=HOLIDAY_AFTER_H) and not coming_home(states, ps):
        return "away_long"
    return None


def summer(days: dict[str, float], now: datetime) -> bool:
    """The last three whole days' average outdoor temperature above 16 °C."""
    last = [days[d] for d in sorted(days) if d < now.date().isoformat()][-3:]
    return len(last) == 3 and sum(last) / 3 > SUMMER_C
