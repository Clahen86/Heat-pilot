"""How sunny each coming hour will be: 0 = overcast, 1 = a clear day - from the best source the home has.

1. A solar power forecast that carries the hours: Solcast (detailedHourly), Open-Meteo Solar Forecast (wh_period).
2. Home Assistant's Energy dashboard solar forecast (Forecast.Solar and the rest) - fetched by the engine.
3. The weather forecast's cloud cover (every home has a weather entity), else its condition.
4. Nothing: the weather right now (sunny / partly cloudy), as before.

A power forecast becomes 0..1 by comparing each hour with the most the panels were forecast to give at that hour of
day lately - a clear-day reference that slowly follows the season. Until that reference has seen a few days, the
cloud cover is used instead (one grey first day must not look like full sun).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

DECAY = 0.98       # the clear-day reference forgets 2 % a day, so it follows the sun down in autumn
MIN_DAYS = 5       # days of power forecast before it is trusted over the cloud cover
SUNNY = {"sunny": 1.0, "clear-night": 1.0, "partlycloudy": 0.5}


def hour_key(dt: datetime) -> int:
    """The hour as a number that is the same in any time zone."""
    return int(dt.timestamp() // 3600)


def pv_from_states(states: dict[str, Any]) -> dict[int, float]:
    """kWh per hour from forecast sensors that carry the hours (several arrays add up)."""
    out: dict[int, float] = {}
    for e, s in states.items():
        if not e.startswith("sensor."):
            continue
        a = (s or {}).get("attributes") or {}
        for p in a.get("detailedHourly") or []:  # Solcast
            try:
                k, kwh = hour_key(datetime.fromisoformat(str(p.get("period_start")))), float(p.get("pv_estimate"))
            except (TypeError, ValueError, AttributeError):
                continue
            out[k] = out.get(k, 0.0) + kwh
        wp = a.get("wh_period")  # Open-Meteo Solar Forecast
        if isinstance(wp, dict):
            for t, wh in wp.items():
                try:
                    k = hour_key(datetime.fromisoformat(str(t)))
                    out[k] = out.get(k, 0.0) + float(wh) / 1000
                except (TypeError, ValueError):
                    continue
    return out


def pv_from_energy(fc: dict[str, Any] | None, ids: list[str]) -> dict[int, float]:
    """kWh per hour from Home Assistant's energy/solar_forecast answer (Forecast.Solar and others)."""
    out: dict[int, float] = {}
    for i in ids:
        for t, wh in ((fc or {}).get(i) or {}).get("wh_hours", {}).items():
            try:
                k = hour_key(datetime.fromisoformat(str(t)))
                out[k] = out.get(k, 0.0) + float(wh) / 1000
            except (TypeError, ValueError):
                continue
    return out


class SunFeed:
    def __init__(self, state: dict[str, Any]) -> None:
        self.s = state.setdefault("sunfeed", {"ref": {}, "days": [], "day": None})
        self.source: str | None = None

    def _learn(self, pv: dict[int, float], now: datetime) -> None:
        """Raise each hour of day's clear-day reference to what the forecast shows; let it fade a little each day."""
        today = now.date().isoformat()
        ref = self.s["ref"]
        if self.s.get("day") != today:
            for h in ref:
                ref[h] = round(ref[h] * DECAY, 4)
            self.s["day"] = today
            if today not in self.s["days"]:
                self.s["days"] = (self.s["days"] + [today])[-30:]
        tz = now.tzinfo
        for k, kwh in pv.items():
            h = str(datetime.fromtimestamp(k * 3600, tz).hour)
            if kwh > ref.get(h, 0.0):
                ref[h] = round(kwh, 4)

    def factors(self, states: dict[str, Any], energy_pv: dict[int, float], clouds: dict[int, float],
                conditions: dict[int, str], now: datetime) -> dict[int, float]:
        """0..1 per coming hour (hour_key -> factor); empty when nothing is known. Sets self.source."""
        pv = pv_from_states(states)
        src = "Solcast / Open-Meteo"
        if not pv:
            pv, src = energy_pv, "Energy dashboard"
        if pv:
            self._learn(pv, now)
        ref, tz = self.s["ref"], now.tzinfo
        if pv and len(self.s["days"]) >= MIN_DAYS:
            out = {}
            for k, kwh in pv.items():
                r = ref.get(str(datetime.fromtimestamp(k * 3600, tz).hour), 0.0)
                if r > 0.05:  # night and dawn: too little to say anything
                    out[k] = round(min(1.0, kwh / r), 2)
            if out:
                self.source = src
                return out
        if clouds:
            self.source = "cloud cover"
            return {k: round(1 - min(100.0, max(0.0, c)) / 100, 2) for k, c in clouds.items()}
        if conditions:
            self.source = "weather forecast"
            return {k: SUNNY.get(c, 0.0) for k, c in conditions.items()}
        self.source = None
        return {}
