"""Ventilation with heat recovery - found by itself, worked out together with the heating.

Most units look alike in Home Assistant, whatever the brand (Dantherm, Nilan, Genvex, Komfovent, Vallox, Zehnder,
Brink, Airmaster, Systemair, Itho …): a fan (a fan entity, or a select of levels), four temperatures (outdoor,
supply, extract, exhaust) and a bypass damper. The unit is the device with a fan control and at least two of the
temperatures.

What it wants, highest first:
- A shower (the bathroom's humidity jumps): boost for half an hour.
- CO2 high in a room (over 1,000 ppm; over 1,400 boost) or humidity high (over 65 %): more air.
- Free cooling: the house is warm (over comfort + 2°) and outside is at least 3° cooler: more air through the bypass,
  and the heating keeps out of it (no heating while the ventilation cools).
- Everyone away: low. Otherwise normal.
Heat recovery is shown: (supply - outdoor) / (extract - outdoor).
"""

from __future__ import annotations

import re
from typing import Any

T_OUT = re.compile(r"outdoor|outside|fresh|ude(luft)?|udendørs|aussen|außen|uteluft|utelu|frisk|t1\b|oda", re.I)
T_SUP = re.compile(r"supply|indblæs|indblaes|zuluft|tilluft|tilluft|insufflation|toevoer|sup\b|t2\b|sup_air", re.I)
T_EXT = re.compile(r"extract|udsug|abluft|frånluft|franluft|avtrekk|reprise|afvoer|eta\b|t3\b|room_air|return_air", re.I)
T_EXH = re.compile(r"exhaust|udblæs|udblaes|fortluft|avluft|avkast|rejet|eha\b|t4\b", re.I)
FAN_LEVEL = re.compile(r"fan|ventilat|level|niveau|speed|stufe|nivå|nivaa|trin", re.I)
NOT_LEVEL = re.compile(r"boost_tilstand|boost_mode_setting|week|uge|program|mode_setting|driftindstilling|operation|eco_|hjemme", re.I)
BYPASS = re.compile(r"bypass", re.I)
VENT_PLATFORMS = ("dantherm", "nilan", "genvex_nordic", "genvexconnect", "komfovent", "vallox", "comfoconnect", "zehnder",
                  "brink_home", "airmaster", "systemair", "swegon", "ithowifi", "itho", "orcon", "flexit", "flexit_bacnet",
                  "salda", "pluggit", "helios", "wolf_comfort", "paul_novus", "duco", "renson")
LEVELS = ("low", "normal", "high", "boost")
CO2_HIGH, CO2_BOOST, HUM_HIGH = 1000, 1400, 65


def _num(states: dict[str, Any], e: str | None) -> float | None:
    s = states.get(e or "") or {}
    try:
        v = float(s.get("state"))
    except (TypeError, ValueError):
        return None
    u = str((s.get("attributes") or {}).get("unit_of_measurement") or "")
    return (v - 32) * 5 / 9 if u in ("°F", "F") else v  # a temperature in °F: in °C like the rest


def find(entities: list[dict[str, Any]], devices: list[dict[str, Any]], states: dict[str, Any]) -> dict[str, Any] | None:
    devs = {d["id"]: d for d in devices}
    by_dev: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        if e.get("device_id") and not e.get("disabled_by") and e["entity_id"] in states:
            by_dev.setdefault(e["device_id"], []).append(e)
    best = None
    for dev, ents in by_dev.items():
        ids = sorted(x["entity_id"] for x in ents)
        temps = [x for x in ids if x.startswith("sensor.") and (states[x].get("attributes") or {}).get("device_class") == "temperature"]

        def t(pat):
            return next((x for x in temps if pat.search(x + " " + str((states[x].get("attributes") or {}).get("friendly_name", "")))), None)

        found = {"outdoor": t(T_OUT), "supply": t(T_SUP), "extract": t(T_EXT), "exhaust": t(T_EXH)}
        fans = [x for x in ids if x.startswith("fan.")]
        levels = [x for x in ids if x.startswith("select.") and FAN_LEVEL.search(x) and not NOT_LEVEL.search(x)
                  and _numeric_options(states[x])]
        plat = next((x.get("platform") for x in ents), None)
        if sum(1 for v in found.values() if v) < 2 or not (fans or levels):
            continue
        if not (plat in VENT_PLATFORMS or (found["supply"] and (found["extract"] or found["exhaust"]))):
            continue
        d = devs.get(dev) or {}
        out = {"device": dev, "name": d.get("name_by_user") or d.get("name") or "Ventilation", "model": d.get("model"),
               "manufacturer": d.get("manufacturer"), "platform": plat, **found,
               "level_select": levels[0] if levels else None, "fan": fans[0] if fans else None,
               "bypass": next((x for x in ids if BYPASS.search(x) and x.split(".")[0] in ("cover", "binary_sensor", "sensor")), None),
               "mode_select": next((x for x in ids if x.startswith("select.") and _is_mode(states[x])), None)}
        if best is None or plat in VENT_PLATFORMS:
            best = out
    return best


def _is_mode(s: dict[str, Any]) -> bool:
    """The unit's own operating mode: a list with manual and automatic in it (Dantherm, Nilan, Komfovent …)."""
    opts = [str(o).lower() for o in (s.get("attributes") or {}).get("options") or []]
    return "manual" in opts and any(o in opts for o in ("automatic", "auto"))


PAUSE_MODES = ("fireplace", "standby", "away", "summer", "week_program")  # chosen on the unit: left alone


def mode_now(unit: dict[str, Any], states: dict[str, Any]) -> str | None:
    return (states.get(unit.get("mode_select") or "") or {}).get("state")


def auto_option(unit: dict[str, Any], states: dict[str, Any]) -> str | None:
    opts = [str(o) for o in ((states.get(unit.get("mode_select") or "") or {}).get("attributes") or {}).get("options") or []]
    return next((o for o in opts if o.lower() in ("automatic", "auto")), None)


def _numeric_options(s: dict[str, Any]) -> list[int]:
    opts = (s.get("attributes") or {}).get("options") or []
    nums = []
    for o in opts:
        m = re.search(r"\d+", str(o))
        if m:
            nums.append(int(m.group()))
    return nums if len(nums) >= 3 else []


def efficiency(unit: dict[str, Any], states: dict[str, Any]) -> float | None:
    o, s, e = _num(states, unit.get("outdoor")), _num(states, unit.get("supply")), _num(states, unit.get("extract"))
    if None in (o, s, e) or e - o < 5:
        return None
    return round(max(0.0, min(1.0, (s - o) / (e - o))) * 100)


def bypass_open(unit: dict[str, Any], states: dict[str, Any]) -> bool | None:
    s = (states.get(unit.get("bypass") or "") or {}).get("state")
    if s is None:
        return None
    return s in ("open", "on", "opening", "1", "true")


def current_level(unit: dict[str, Any], states: dict[str, Any]) -> str | None:
    """The unit's level now, as low/normal/high/boost."""
    if unit.get("level_select"):
        s = states.get(unit["level_select"]) or {}
        nums = sorted(set(_numeric_options(s)))
        m = re.search(r"\d+", str(s.get("state")))
        if m and nums:
            return _to_level(int(m.group()), nums)
    if unit.get("fan"):
        p = ((states.get(unit["fan"]) or {}).get("attributes") or {}).get("percentage")
        if isinstance(p, (int, float)):
            return "low" if p < 30 else "normal" if p < 55 else "high" if p < 85 else "boost"
    return None


def current_step(unit: dict[str, Any], states: dict[str, Any]) -> tuple[int | None, int | None]:
    """The step the unit runs on now, as the unit counts it (1-4 on a Dantherm), and how many steps it has."""
    if unit.get("level_select"):
        s = states.get(unit["level_select"]) or {}
        nums = sorted(x for x in set(_numeric_options(s)) if x > 0)
        m = re.search(r"\d+", str(s.get("state")))
        if m and nums:
            return int(m.group()), max(nums)
    if unit.get("fan"):
        p = ((states.get(unit["fan"]) or {}).get("attributes") or {}).get("percentage")
        if isinstance(p, (int, float)):
            return max(1, min(4, round(p / 25))), 4
    return None, None


def _to_level(n: int, nums: list[int]) -> str:
    usable = [x for x in nums if x > 0] or nums  # 0 is off on most units - never chosen
    i = usable.index(n) if n in usable else 0
    frac = i / max(1, len(usable) - 1)
    return "low" if frac < 0.25 else "normal" if frac < 0.5 else "high" if frac < 0.85 else "boost"


def level_value(unit: dict[str, Any], states: dict[str, Any], level: str) -> Any:
    """The option / percentage that means this level on this unit."""
    if unit.get("level_select"):
        s = states.get(unit["level_select"]) or {}
        opts = (s.get("attributes") or {}).get("options") or []
        pairs = [(int(m.group()), o) for o in opts if (m := re.search(r"\d+", str(o)))]
        usable = sorted([p for p in pairs if p[0] > 0] or pairs)
        idx = {"low": 0, "normal": 1, "high": len(usable) - 2, "boost": len(usable) - 1}[level]
        return usable[max(0, min(len(usable) - 1, idx))][1]
    return {"low": 20, "normal": 40, "high": 70, "boost": 100}[level]


def calls(unit: dict[str, Any], states: dict[str, Any], level: str) -> list[dict[str, Any]]:
    """What to send for this level - only what isn't so already. A unit with its own mode is put in manual first."""
    v = level_value(unit, states, level)
    out = []
    ms = unit.get("mode_select")
    if ms and str((states.get(ms) or {}).get("state")).lower() != "manual":
        out.append({"domain": "select", "service": "select_option", "data": {"entity_id": ms, "option": "manual"}})
    if unit.get("level_select"):
        if str((states.get(unit["level_select"]) or {}).get("state")) != str(v):
            out.append({"domain": "select", "service": "select_option", "data": {"entity_id": unit["level_select"], "option": v}})
        return out
    p = ((states.get(unit.get("fan") or "") or {}).get("attributes") or {}).get("percentage")
    if p is None or abs(float(p) - float(v)) > 3:
        out.append({"domain": "fan", "service": "set_percentage", "data": {"entity_id": unit["fan"], "percentage": v}})
    return out


def handback_calls(unit: dict[str, Any], states: dict[str, Any]) -> list[dict[str, Any]]:
    """Heat Pilot lets go: the unit back to its own automatic mode (when it has one)."""
    opt = auto_option(unit, states)
    if unit.get("mode_select") and opt:
        return [{"domain": "select", "service": "select_option", "data": {"entity_id": unit["mode_select"], "option": opt}}]
    return []


def _old_calls(unit: dict[str, Any], states: dict[str, Any], level: str) -> list[dict[str, Any]]:
    v = level_value(unit, states, level)
    if unit.get("level_select"):
        return [{"domain": "select", "service": "select_option", "data": {"entity_id": unit["level_select"], "option": v}}]
    return [{"domain": "fan", "service": "set_percentage", "data": {"entity_id": unit["fan"], "percentage": v}}]


def decide(rooms: list[dict[str, Any]], states: dict[str, Any], shower: bool, away: bool, house_temp: float | None,
           comfort: float, outdoor: float | None) -> dict[str, Any]:
    """{"level": low/normal/high/boost, "why": key, "cooling": bool}."""
    co2 = [v for r in rooms for e in r.get("co2") or [] if (v := _num(states, e)) is not None]
    hum = [v for r in rooms if r.get("kind") != "bathroom" for e in r.get("humidity") or [] if (v := _num(states, e)) is not None]
    if shower:
        return {"level": "boost", "why": "shower", "cooling": False}
    if co2 and max(co2) >= CO2_HIGH + 400:
        return {"level": "boost", "why": "co2", "cooling": False}
    if co2 and max(co2) >= CO2_HIGH:
        return {"level": "high", "why": "co2", "cooling": False}
    if hum and max(hum) >= HUM_HIGH:
        return {"level": "high", "why": "humidity", "cooling": False}
    if house_temp is not None and outdoor is not None and house_temp >= comfort + 2 and outdoor <= house_temp - 3 and outdoor >= 10:
        return {"level": "high", "why": "free_cooling", "cooling": True}
    if away:
        return {"level": "low", "why": "away", "cooling": False}
    return {"level": "normal", "why": "normal", "cooling": False}


def other_cooling(states: dict[str, Any], entity: str | None) -> bool:
    """Another system says it is cooling (a switch, a binary sensor, or a sensor with a precool/cooling attribute)."""
    if not entity:
        return False
    s = states.get(entity) or {}
    if str(s.get("state")).lower() in ("on", "true", "cool", "cooling", "precool", "køle", "kole"):
        return True
    a = s.get("attributes") or {}
    return any(str(a.get(k)).lower() in ("true", "on", "1") for k in ("precool", "cooling", "free_cooling"))
