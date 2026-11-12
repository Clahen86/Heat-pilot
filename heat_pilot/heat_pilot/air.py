"""The air in each room, and what the ventilation should do about it - one level for the whole house.

A central unit can't air one room: it blows fresh air into some rooms (bedrooms, living rooms) and draws used air
out of others (bathroom, kitchen, laundry). So each room counts for what the air can do there:
- where air is drawn out: damp counts - a shower or cooking shows as a quick rise over the room's own normal level.
- where fresh air comes in: CO2 counts, and damp only when it is high over a long time.
- a room with no vents doesn't count at all.
Fine dust (PM2.5 - smoke, cooking, a wood stove) counts anywhere. More air only helps against damp when the air
outside is drier than inside; on a mild, wet day more air brings damp in, so it isn't raised for that.
The room that decides is told, so the house can show why.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import math
import re
from statistics import median
from typing import Any

from .discover import room_kind

OUT_WORDS = re.compile(r"bad|bath|wc|toilet|køkken|kokken|kitchen|küche|kueche|kjøkken|kök|kok\b|vask|laundry|bryggers|utility|"
                       r"waschk|tvätt|tvatt|grovkøkken|cuisine|salle de bain|keuken|badkamer|wasruimte", re.I)
NONE_WORDS = re.compile(r"garage|carport|skur|shed|udhus|kælder ?rum|loft\b|attic|træning|traening|gym|værksted|vaerksted|workshop", re.I)
CO2_HIGH, CO2_BOOST = 1000, 1200   # shown as yellow from 1000; more air only from 1200 - and then full air:
# measured on a real house over 30 days, the middle levels hardly lowered CO2 at all; only the top level did
COLD = 8.0                           # colder than this outside: when the air is fine, low - less heat thrown out
HUM_HIGH = 65
RISE, RISE_MIN, RISE_HOLD = 8.0, 15, 30          # % in 15 min = someone showers or cooks; hold the extra air 30 min
PM_HIGH, PM_BOOST = 35, 75                        # µg/m³
NIGHT = range(23, 24), range(0, 6)


def airflow(room: dict[str, Any], own: dict[str, Any] | None = None) -> str:
    """supply (fresh air in), exhaust (used air out) or none - as set, else from the room's name."""
    set_to = (own or {}).get("airflow")
    if set_to in ("supply", "exhaust", "none"):
        return set_to
    name = room.get("name") or ""
    if room.get("kind") == "bathroom" or OUT_WORDS.search(name):
        return "exhaust"
    if NONE_WORDS.search(name):
        return "none"
    return "supply"


def find_air_rooms(areas: list[dict[str, Any]], devices_list: list[dict[str, Any]], entities: list[dict[str, Any]],
                   states: dict[str, Any], heated: set[str]) -> list[dict[str, Any]]:
    """Rooms with no heating Heat Pilot runs but with air sensors (a kitchen, a laundry): they count for the air."""
    devices = {d["id"]: d for d in devices_list}
    names = {a["area_id"]: a.get("name") or a["area_id"] for a in areas}
    floors = {a["area_id"]: a.get("floor_id") for a in areas}
    found: dict[str, dict[str, list[str]]] = {}
    for e in entities:
        eid = e["entity_id"]
        if e.get("disabled_by") or not eid.startswith("sensor.") or eid not in states:
            continue
        area = e.get("area_id") or (devices.get(e.get("device_id") or "") or {}).get("area_id")
        if not area or area in heated:
            continue
        dc = (states[eid].get("attributes") or {}).get("device_class")
        key = {"humidity": "humidity", "carbon_dioxide": "co2", "pm25": "pm25"}.get(dc)
        if key:
            found.setdefault(area, {}).setdefault(key, []).append(eid)
    out = []
    for area, s in sorted(found.items()):
        name = names.get(area, area)
        out.append({"area_id": area, "name": name, "kind": room_kind(name), "floor_id": floors.get(area), "air_only": True,
                    "humidity": sorted(s.get("humidity", []))[:1], "co2": sorted(s.get("co2", []))[:1], "pm25": sorted(s.get("pm25", []))[:1]})
    return out


def _num(states: dict[str, Any], e: str | None) -> float | None:
    try:
        return float((states.get(e or "") or {}).get("state"))
    except (TypeError, ValueError):
        return None


def dewpoint(temp: float | None, rh: float | None) -> float | None:
    if temp is None or rh is None or rh <= 0:
        return None
    a, b = 17.62, 243.12
    g = math.log(rh / 100) + a * temp / (b + temp)
    return round(b * g / (a - g), 1)


class AirWatch:
    """Each room's damp over the last day (its normal level) and quick rises (a shower, cooking)."""

    def __init__(self) -> None:
        self.hist: dict[str, deque] = {}
        self.until: dict[str, datetime] = {}
        self.peak: dict[str, float] = {}
        self.rise = RISE

    def see(self, area: str, hum: float | None, now: datetime) -> None:
        if hum is None:
            return
        h = self.hist.setdefault(area, deque(maxlen=300))
        if not h or (now - h[-1][0]).total_seconds() >= 240 or abs(hum - h[-1][1]) >= 2:
            h.append((now, hum))
        old = [v for t, v in h if timedelta(minutes=RISE_MIN - 3) <= now - t <= timedelta(minutes=RISE_MIN + 5)]
        if old and hum - min(old) >= self.rise:
            self.until[area] = now + timedelta(minutes=RISE_HOLD)
            self.peak[area] = hum
        # back near its normal level: the extra air can stop early
        if area in self.until and hum <= self.normal(area, now) + 3:
            self.until.pop(area, None)

    def normal(self, area: str, now: datetime) -> float:
        vals = [v for t, v in self.hist.get(area) or () if now - t <= timedelta(hours=24)]
        return median(vals) if vals else 50.0

    def rising(self, area: str, now: datetime) -> bool:
        return now < self.until.get(area, now)

    def left(self, area: str, now: datetime) -> int | None:
        u = self.until.get(area)
        return max(0, round((u - now).total_seconds() / 60)) if u and u > now else None


def decide(rooms: list[dict[str, Any]], states: dict[str, Any], watch: AirWatch, now: datetime, *, away: bool,
           house_temp: float | None, comfort: float, outdoor: float | None, outdoor_dp: float | None,
           own: dict[str, dict[str, Any]] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"level", "why", "lead": {area_id, name, value, unit, minutes} | None, "cooling"}."""
    own = own or {}
    pr = params or {}
    co2_boost = float(pr.get("co2_boost") or CO2_BOOST)
    hum_high = float(pr.get("humidity_high") or HUM_HIGH)
    pm_boost = float(pr.get("pm25_boost") or PM_BOOST)
    pm_high = min(PM_HIGH, pm_boost)
    watch.rise = float(pr.get("humidity_rise") or RISE)
    lead = None

    def pick(level: str, why: str, r: dict[str, Any] | None = None, value: float | None = None, unit: str | None = None,
             cooling: bool = False) -> dict[str, Any]:
        if r is not None:
            nonlocal lead
            lead = {"area_id": r["area_id"], "name": r["name"], "value": None if value is None else round(value), "unit": unit,
                    "minutes": watch.left(r["area_id"], now)}
        return {"level": level, "why": why, "lead": lead, "cooling": cooling}

    seen = []
    for r in rooms:
        flow = airflow(r, own.get(r["area_id"]))
        if flow == "none":
            continue
        hum = _num(states, (r.get("humidity") or [None])[0])
        co2 = _num(states, (r.get("co2") or [None])[0])
        pm = _num(states, (r.get("pm25") or [None])[0])
        watch.see(r["area_id"], hum, now)
        seen.append((r, flow, hum, co2, pm))

    def damp_helps(r: dict[str, Any], hum: float | None) -> bool:
        """More air only dries a room when the air outside holds less water than the room's air."""
        if outdoor_dp is None or hum is None:
            return True
        t = _num(states, r.get("temp_sensor")) or house_temp or 21.0
        inside = dewpoint(t, hum)
        return inside is None or outdoor_dp < inside - 1

    # 1. A shower or cooking: the room's damp jumped - full air until it's back near its normal level.
    wet = [(r, hum) for r, flow, hum, _c, _p in seen if flow == "exhaust" and watch.rising(r["area_id"], now)]
    if wet:
        r, hum = max(wet, key=lambda x: x[1] or 0)
        return pick("boost", "shower" if r.get("kind") == "bathroom" else "damp", r, hum, "%")
    # 2. Smoke or fine dust anywhere.
    dust = [(r, pm) for r, _f, _h, _c, pm in seen if pm is not None and pm >= pm_high]
    if dust:
        r, pm = max(dust, key=lambda x: x[1])
        return pick("boost" if pm >= pm_boost else "high", "dust", r, pm, "µg/m³")
    # 3. Stale air where fresh air comes in: full air, or nothing extra (a middle level doesn't lower CO2).
    stale = [(r, co2) for r, flow, _h, co2, _p in seen if flow == "supply" and co2 is not None and co2 >= co2_boost]
    if stale:
        r, co2 = max(stale, key=lambda x: x[1])
        return pick("boost", "co2", r, co2, "ppm")
    # 4. Damp that stays high, when more air can dry it.
    damp = [(r, hum) for r, _f, hum, _c, _p in seen if hum is not None and hum >= hum_high and damp_helps(r, hum)]
    if damp:
        r, hum = max(damp, key=lambda x: x[1])
        return pick("high", "humidity", r, hum, "%")
    # 5. Free cooling: the house is warm and the evening outside is cool.
    if house_temp is not None and outdoor is not None and house_temp >= comfort + 2 and 10 <= outdoor <= house_temp - 3:
        return pick("high", "free_cooling", cooling=True)
    if away:
        return pick("low", "away")
    if now.hour >= 23 or now.hour < 6:
        return pick("low", "night")
    if outdoor is not None and outdoor < COLD:
        return pick("low", "save_heat")
    return pick("normal", "normal")


def params_from_appdaemon(states: dict[str, Any]) -> dict[str, Any]:
    """An AppDaemon indoor-climate app already learned this house's limits: start from them."""
    a = (states.get("sensor.indeklima_learning") or {}).get("attributes") or {}
    out = {}
    for mine, theirs in (("co2_boost", "co2_boost"), ("humidity_rise", "humidity_rise_pct"), ("pm25_boost", "pm25_boost")):
        try:
            if a.get(theirs) is not None:
                out[mine] = float(a[theirs])
        except (TypeError, ValueError):
            pass
    return out


def room_air(room: dict[str, Any], states: dict[str, Any], own: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the house shows on a room: its vents and the colour of its air (good / warn / bad)."""
    flow = airflow(room, own)
    hum = _num(states, (room.get("humidity") or [None])[0])
    co2 = _num(states, (room.get("co2") or [None])[0])
    pm = _num(states, (room.get("pm25") or [None])[0])
    level = "good"
    if (co2 is not None and co2 >= CO2_BOOST) or (pm is not None and pm >= PM_BOOST) or (hum is not None and hum >= 75):
        level = "bad"
    elif (co2 is not None and co2 >= CO2_HIGH) or (pm is not None and pm >= PM_HIGH) or (hum is not None and hum >= HUM_HIGH):
        level = "warn"
    return {"airflow": flow, "co2": None if co2 is None else round(co2), "hum": None if hum is None else round(hum),
            "pm25": None if pm is None else round(pm), "air": level if flow != "none" else None}


def outdoor_dewpoint(states: dict[str, Any]) -> float | None:
    """From the weather: its own dew point, else from its temperature and humidity."""
    for e, s in states.items():
        if e.startswith("weather."):
            a = s.get("attributes") or {}
            try:
                if a.get("dew_point") is not None:
                    return float(a["dew_point"])
                return dewpoint(float(a.get("temperature")), float(a.get("humidity")))
            except (TypeError, ValueError):
                return None
    return None
