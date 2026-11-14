"""Hot water as a small battery: the tank is heated when power is cheap and allowed to cool in the dear hours -
never below the lowest temperature, warm in time for the showers, and a weekly heat-up against legionella.

Works with a water heater in Home Assistant (water_heater.*: heat pumps with a tank, smart water heaters) or an
immersion heater on a switch (switch.*), best with a temperature sensor in the tank. Starts in shadow like the rooms.
Homes whose hot water comes from district heating have nothing to gain - it is only offered when a tank is found.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

WORDS = re.compile(r"water_heater|varmtvand|varmvann|varmvatten|hot_?water|dhw|boiler|elpatron|immersion|warmwasser|"
                   r"tank|vvb|beholder|cumulus|chauffe_eau|ballon|warmtepomp_boiler", re.I)
DEFAULT = {"min": 45.0, "normal": 52.0, "max": 60.0, "legionella": 65.0, "ready": ["06:30", "19:00"]}
LEGIONELLA_DAYS = 7


def find(states: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """What could be the tank: water heaters, switches that look like an immersion heater, and tank temperature sensors."""
    def nm(e: str) -> str:
        return ((states.get(e) or {}).get("attributes") or {}).get("friendly_name") or e
    heaters = [e for e in states if e.startswith("water_heater.")]
    switches = [e for e in states if e.startswith("switch.") and WORDS.search(e + " " + nm(e))]
    temps = [e for e, s in states.items() if e.startswith("sensor.") and (s.get("attributes") or {}).get("device_class") == "temperature"
             and WORDS.search(e + " " + nm(e))]
    return {k: [{"entity_id": e, "name": nm(e)} for e in sorted(v)] for k, v in (("heaters", heaters), ("switches", switches), ("temps", temps))}


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def temp_now(cfg: dict[str, Any], states: dict[str, Any]) -> float | None:
    if cfg.get("temp"):
        return _num((states.get(cfg["temp"]) or {}).get("state"))
    if (e := cfg.get("entity") or "").startswith("water_heater."):
        return _num(((states.get(e) or {}).get("attributes") or {}).get("current_temperature"))
    return None


def _ready_soon(cfg: dict[str, Any], now: datetime, hours: float = 2.0) -> bool:
    for t in cfg.get("ready") or []:
        try:
            h, m = (int(x) for x in str(t).split(":")[:2])
        except ValueError:
            continue
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if at < now - timedelta(minutes=30):
            at += timedelta(days=1)
        if now - timedelta(minutes=30) <= at and at - now <= timedelta(hours=hours):
            return True
    return False


def decide(cfg: dict[str, Any], state: dict[str, Any], states: dict[str, Any], level: str | None, now: datetime) -> dict[str, Any] | None:
    """The tank's temperature to aim for now, and why. `state` keeps when it was last hot enough against legionella."""
    e = cfg.get("entity") or ""
    if not e or e not in states:
        return None
    c = {**DEFAULT, **{k: v for k, v in cfg.items() if v not in (None, "")}}
    t = temp_now(cfg, states)
    if t is not None and t >= float(c["legionella"]) - 1:
        state["hot"] = now.isoformat()
    last_hot = datetime.fromisoformat(state["hot"]) if state.get("hot") else None
    legion_due = last_hot is None or now - last_hot >= timedelta(days=LEGIONELLA_DAYS)
    if legion_due and (level == "cheap" or (last_hot is not None and now - last_hot >= timedelta(days=LEGIONELLA_DAYS + 1))):
        target, why = float(c["legionella"]), "legionella"
    elif level == "cheap":
        target, why = float(c["max"]), "cheap"
    elif _ready_soon(c, now):
        target, why = float(c["normal"]), "ready"
    elif level == "dear":
        target, why = float(c["min"]), "dear"
    else:
        target, why = float(c["normal"]), "normal" if level else "no_price"
    heat = None if t is None else t < target - (0 if e.startswith("water_heater.") else 2)
    return {"target": target, "why": why, "temp": t, "heating": heat, "level": level, "calls": calls(e, target, t, why, states),
            "last_hot": state.get("hot"), "mode": cfg.get("mode") or "shadow", "entity": e}


def calls(e: str, target: float, t: float | None, why: str, states: dict[str, Any]) -> list[dict[str, Any]]:
    st = states.get(e) or {}
    if e.startswith("water_heater."):
        a = st.get("attributes") or {}
        lo, hi = _num(a.get("min_temp")) or 30.0, _num(a.get("max_temp")) or 75.0
        val = round(max(lo, min(hi, target)))
        if _num(a.get("temperature")) == val:
            return []
        return [{"domain": "water_heater", "service": "set_temperature", "data": {"entity_id": e, "temperature": val}}]
    if e.startswith("switch."):
        if t is None:  # no thermometer: the tank's own thermostat keeps the temperature - only off in the dear hours
            on = why != "dear"
        elif t >= target:
            on = False
        elif t < target - 2:
            on = True
        else:
            return []  # in between: leave it as it is
        if st.get("state") == ("on" if on else "off"):
            return []
        return [{"domain": "switch", "service": f"turn_{'on' if on else 'off'}", "data": {"entity_id": e}}]
    return []


def handback(cfg: dict[str, Any], states: dict[str, Any]) -> list[dict[str, Any]]:
    """Back to shadow: the tank to its normal temperature (or the immersion heater on, with its own thermostat)."""
    e = cfg.get("entity") or ""
    c = {**DEFAULT, **{k: v for k, v in cfg.items() if v not in (None, "")}}
    if e.startswith("water_heater."):
        return calls(e, float(c["normal"]), None, "normal", states)
    if e.startswith("switch.") and (states.get(e) or {}).get("state") == "off":
        return [{"domain": "switch", "service": "turn_on", "data": {"entity_id": e}}]
    return []
