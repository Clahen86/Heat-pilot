"""Where the heat comes from - and what that means for when and how to heat.

District heating: the bill has a bonus or a penalty for cooling - how much the water cools in the house (supply
minus return). A heat meter in Home Assistant (Kamstrup, Danfoss, Landis+Gyr, Sensus … via an IR reader, M-Bus
or the utility) with a supply and a return temperature is found by itself. Shown: the cooling now and over the
day (weighted by the water that ran, the way utilities settle it), and the bonus or penalty it is heading for.
When cooling is poor, heating up is spread out: rooms warm gently over a longer time instead of every valve wide
open at once - which lowers the return temperature.

Electric heating and heat pumps: rooms heated by electricity follow the price - a little warmer in the cheapest
hours and a little cooler in the dearest, always within the comfort band. The price comes from the same
integrations Energy Pilot reads (Nordpool, Energi Data Service, Strømligning, Tibber, Octopus …).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo

from . import pricefeed

PRICE_PLATFORMS = ("stromligning", "nordpool", "energidataservice", "tibber", "octopus_energy", "entsoe", "easyenergy",
                   "frank_energie", "awattar", "zonneplan_one", "amber", "elering")
HEAT_PUMP_PLATFORMS = ("daikin", "daikin_onecta", "melcloud", "mitsubishi", "panasonic_cc", "aquarea", "nibe_heatpump",
                       "myuplink", "mypyllant", "vicare", "sensibo", "gree", "midea_ac_lan", "fujitsu_hvac", "toshiba_ac",
                       "lg_thinq", "samsung_ac", "nilan", "thermia", "stiebel_eltron", "ochsner", "idm_heatpump")
SUPPLY = re.compile(r"supply|forward|flow_temp|fremløb|fremlob|frem_temp|vorlauf|framledning|tillopp|temperature_1|t1\b", re.I)
RETURN = re.compile(r"return|retur|rücklauf|rucklauf|returledning|temperature_2|t2\b", re.I)
FLOW = re.compile(r"flow_rate|flow|gennemstrømning|durchfluss|volume_flow", re.I)
VOLUME = re.compile(r"volume|m3|vandmængde|volumen", re.I)
STATS = re.compile(r"avg|average|mean|gennemsnit|durchschnitt|\bmin\b|_min_|min_|\bmax\b|_max_|max_|month|year|week|day\b|daily|"
                   r"monthly|yearly|weekly|måned|maned|år\b|total|peak|target|setpoint", re.I)
DH_WORDS = re.compile(r"kamstrup|multical|heat_meter|varmemåler|varmemaler|fjernvarme|district|wärmezähler|fernwärme|"
                      r"fjärrvärme|sensus|landis|ultrego|sharky|qundis|danfoss_sonometer|sonometer|heat_energy", re.I)


def find_heat_meter(entities: list[dict[str, Any]], devices: list[dict[str, Any]], states: dict[str, Any]) -> dict[str, str] | None:
    """A device with both a supply and a return temperature (and preferably flow/volume) - a district heating meter."""
    devs = {d["id"]: d for d in devices}
    by_dev: dict[str, list[str]] = {}
    for e in entities:
        if e["entity_id"].startswith("sensor.") and e.get("device_id") and not e.get("disabled_by") and e["entity_id"] in states:
            by_dev.setdefault(e["device_id"], []).append(e["entity_id"])
    best = None
    for dev, ents in by_dev.items():
        def first(pat, cls=None, unit=None):
            # The live value: never an average, a minimum or a maximum over a day/month/year (Kamstrup readers have
            # "Avg Temperature 1 (Month)" beside "Temperature 1 Supply"); names that say supply/return first.
            live = [x for x in sorted(ents) if not STATS.search(x + " " + str((states[x].get("attributes") or {}).get("friendly_name", "")))]
            live.sort(key=lambda x: not re.search(r"supply|forward|fremløb|fremlob|vorlauf|return|retur|rücklauf", x, re.I))
            for x in live:
                a = states[x].get("attributes") or {}
                text = f"{x} {a.get('friendly_name', '')}"
                if pat.search(text) and (cls is None or a.get("device_class") == cls) and \
                        (unit is None or str(a.get("unit_of_measurement") or "").lower() in unit):
                    return x
            return None
        sup = first(SUPPLY, "temperature")
        ret = first(RETURN, "temperature")
        if not (sup and ret) or sup == ret:
            continue
        d = devs.get(dev) or {}
        named = DH_WORDS.search(" ".join(str(d.get(k) or "") for k in ("manufacturer", "model", "name")) + " " + " ".join(ents))
        out = {"supply": sup, "return": ret, "flow": first(FLOW, None, ("m³/h", "m3/h", "l/h", "l/min")),
               "volume": first(VOLUME, None, ("m³", "m3")), "device": dev}
        if named or out["flow"] or out["volume"]:
            if best is None or named:
                best = out
    return best


def _num(states: dict[str, Any], e: str | None) -> float | None:
    try:
        return float((states.get(e or "") or {}).get("state"))
    except (TypeError, ValueError):
        return None


class Cooling:
    """The day's cooling weighted by the water that ran (supply - return), kept a minute at a time."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.s = state.setdefault("cooling", {})
        self._vol: float | None = None

    def see(self, meter: dict[str, str] | None, states: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        if not meter:
            return None
        if self.s.get("_meter") != meter["supply"]:
            # Another sensor than before (or the wrong one was used): what was kept is not this meter's.
            for k in [k for k in self.s if not k.startswith("_")]:
                self.s.pop(k, None)
            self.s["_meter"] = meter["supply"]
            self._vol = None
        sup, ret = _num(states, meter["supply"]), _num(states, meter["return"])
        if sup is None or ret is None:
            return None
        vol = _num(states, meter.get("volume"))
        weight = 1.0
        if vol is not None:
            weight = max(0.0, vol - self._vol) if self._vol is not None else 0.0
            self._vol = vol
        elif (fl := _num(states, meter.get("flow"))) is not None:
            weight = max(0.0, fl)
        day = self.s.setdefault(now.date().isoformat(), {"w": 0.0, "wdt": 0.0, "wret": 0.0})
        day["w"] += weight
        day["wdt"] += weight * (sup - ret)
        day["wret"] += weight * ret
        for old in sorted(k for k in self.s if not k.startswith("_"))[:-400]:
            self.s.pop(old, None)
        return {"supply": sup, "return": ret, "now": round(sup - ret, 1)}

    def period(self, days: list[str]) -> float | None:
        w = sum(self.s[d]["w"] for d in days if d in self.s)
        return round(sum(self.s[d]["wdt"] for d in days if d in self.s) / w, 1) if w > 0 else None

    def summary(self, now: datetime, need: float | None, penalty: float | None, bonus: float | None) -> dict[str, Any]:
        today = now.date().isoformat()
        days = sorted(k for k in self.s if not k.startswith("_"))
        year = [d for d in days if d.startswith(str(now.year))]
        out = {"today": self.period([today]), "week": self.period(days[-7:]), "year": self.period(year), "need": need}
        if need is not None and out["year"] is not None:
            diff = out["year"] - need
            out["per_mwh"] = round(diff * (bonus or 0) if diff > 0 else diff * (penalty or 0), 2)  # + bonus, - penalty
        return out


def poor_cooling(info: dict[str, Any] | None, need: float | None) -> bool:
    return bool(info and need and info.get("today") is not None and info["today"] < need - 2)


def find_price(entities: list[dict[str, Any]], states: dict[str, Any], tz: ZoneInfo) -> str | None:
    now = datetime.now(tz)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for e in sorted(entities, key=lambda x: x["entity_id"]):
        if e.get("platform") in PRICE_PLATFORMS and e["entity_id"].startswith("sensor.") and e["entity_id"] in states:
            if len(pricefeed.parse(states[e["entity_id"]].get("attributes") or {}, tz, day0)) >= 12:
                return e["entity_id"]
    return None


def price_level(prices: dict[datetime, float], now: datetime) -> str | None:
    """The hour now against the coming day's prices: "cheap" (cheapest quarter), "dear" (dearest quarter) or "mid"."""
    ahead = sorted(v for k, v in prices.items() if now.replace(minute=0, second=0, microsecond=0) <= k < now + timedelta(hours=24))
    past = [k for k in prices if k <= now]
    if len(ahead) < 8 or not past:
        return None
    cur = prices[max(past)]
    lo, hi = ahead[len(ahead) // 4], ahead[(3 * len(ahead)) // 4]
    return "cheap" if cur <= lo else "dear" if cur >= hi else "mid"


def is_electric(room: dict[str, Any]) -> bool:
    if room.get("heating") in ("heatpump", "electric"):
        return True
    return any(t.get("platform") in HEAT_PUMP_PLATFORMS for t in room.get("thermostats") or [])
