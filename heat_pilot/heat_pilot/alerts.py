"""Keeping an eye on the house - shown in the app, and sent as a message only if you choose.

Each kind can be turned off on its own, and messages go only to the phones chosen (none until chosen). The same
warning is sent at most once every 12 hours, and not at night unless allowed.

- mold: humidity at 70 % or more for 6 hours - or a cold room (under 16°) at 65 % or more
- air: CO2 over 1,200 ppm for half an hour
- window: a window open for 30 minutes while it is under 10° outside
- offline: a thermostat that has been unavailable for 30 minutes
- battery: a thermostat's or room sensor's battery under 15 %
- not_warming: a room that has been heating for 3 hours and is still more than a degree below its target -
  air in the radiator, a valve stuck, or a radiator too small
- cooling: district heating cooling well below what is required today
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

KINDS = ["mold", "air", "window", "offline", "battery", "not_warming", "cooling", "monthly"]
REPEAT_H = 12


def _num(states: dict[str, Any], e: str | None) -> float | None:
    try:
        return float((states.get(e or "") or {}).get("state"))
    except (TypeError, ValueError):
        return None


def _since(s: dict[str, Any] | None) -> datetime | None:
    try:
        return datetime.fromisoformat((s or {})["last_changed"])
    except (KeyError, ValueError, TypeError):
        return None


class Alerts:
    def __init__(self, state: dict[str, Any]) -> None:
        self.s = state.setdefault("alerts", {"sent": {}})
        self.since: dict[str, datetime] = {}  # condition key -> since when it has been true
        self.active: list[dict[str, Any]] = []

    def _hold(self, key: str, true: bool, now: datetime, minutes: float) -> bool:
        """True once the condition has held for `minutes`."""
        if not true:
            self.since.pop(key, None)
            return False
        start = self.since.setdefault(key, now)
        return (now - start).total_seconds() >= minutes * 60

    def check(self, rooms: list[dict[str, Any]], now_rooms: dict[str, dict[str, Any]], states: dict[str, Any], now: datetime,
              outdoor: float | None, cooling: dict[str, Any] | None) -> list[dict[str, Any]]:
        out = []
        for r in rooms:
            a, name = r["area_id"], r["name"]
            n = now_rooms.get(a) or {}
            temp = n.get("temp")
            hum = _num(states, (r.get("humidity") or [None])[0])
            co2 = _num(states, (r.get("co2") or [None])[0])
            if hum is not None and r.get("kind") != "bathroom":
                cold_damp = temp is not None and temp < 16 and hum >= 65
                if self._hold(f"mold:{a}", hum >= 70 or cold_damp, now, 0 if cold_damp else 360):
                    out.append({"kind": "mold", "room": name, "key": f"mold:{a}", "hum": round(hum), "temp": temp})
            if co2 is not None and self._hold(f"air:{a}", co2 >= 1200, now, 30):
                out.append({"kind": "air", "room": name, "key": f"air:{a}", "co2": round(co2)})
            for w in r.get("windows") or []:
                s = states.get(w) or {}
                t = _since(s)
                if s.get("state") == "on" and t and (now - t) >= timedelta(minutes=30) and outdoor is not None and outdoor < 10:
                    out.append({"kind": "window", "room": name, "key": f"window:{w}", "minutes": int((now - t).total_seconds() // 60)})
            for th in r.get("thermostats") or []:
                s = states.get(th["entity_id"]) or {}
                t = _since(s)
                if s.get("state") in ("unavailable", "unknown") and t and (now - t) >= timedelta(minutes=30):
                    out.append({"kind": "offline", "room": name, "key": f"offline:{th['entity_id']}", "device": th["name"]})
            for b in r.get("batteries") or []:
                v = _num(states, b)
                if v is not None and v < 15:
                    out.append({"kind": "battery", "room": name, "key": f"battery:{b}", "level": round(v),
                                "device": (states.get(b) or {}).get("attributes", {}).get("friendly_name") or b})
            want = (n.get("want") or {}).get("temp")
            heating = bool(n.get("heating"))
            below = temp is not None and want is not None and temp < want - 1
            if self._hold(f"warm:{a}", heating and below, now, 180):
                out.append({"kind": "not_warming", "room": name, "key": f"warm:{a}", "temp": temp, "want": want})
        if cooling and cooling.get("today") is not None and cooling.get("need") and now.hour >= 18 \
                and cooling["today"] < cooling["need"] - 5:
            out.append({"kind": "cooling", "room": "", "key": f"cooling:{now.date()}", "today": cooling["today"], "need": cooling["need"]})
        self.active = out
        return out

    def to_send(self, settings: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
        """The warnings due to be sent now: kind turned on, recipients chosen, not sent lately, not at night."""
        cfg = settings.get("messages") or {}
        if not cfg.get("targets"):
            return []
        if not cfg.get("night") and (now.hour >= 22 or now.hour < 7):
            return []
        off = set(k for k, v in (cfg.get("kinds") or {}).items() if v is False)
        due = []
        for a in self.active:
            if a["kind"] in off:
                continue
            last = self.s["sent"].get(a["key"])
            if last and now - datetime.fromisoformat(last) < timedelta(hours=REPEAT_H):
                continue
            self.s["sent"][a["key"]] = now.isoformat()
            due.append(a)
        for k in [k for k, v in self.s["sent"].items() if k != "monthly" and now - datetime.fromisoformat(v) > timedelta(days=3)]:
            self.s["sent"].pop(k, None)
        return due


TEXT = {
    "da": {"mold": "Skimmelrisiko i {room}: {hum} % fugt. Luft ud, og hold rummet varmere.",
           "air": "Dårlig luft i {room} ({co2} ppm CO₂). Luft ud et par minutter.",
           "window": "Vinduet i {room} har været åbent i {minutes} min. Varmen er slukket imens.",
           "offline": "{device} i {room} svarer ikke. Tjek batteri eller forbindelse.",
           "battery": "{device} har {level} % tilbage – skift batteriet.",
           "not_warming": "{room} bliver ikke varmt ({temp}° af {want}°). Måske luft i radiatoren eller en ventil, der sidder fast.",
           "cooling": "Fjernvarmen: afkøling {today}° i dag – kravet er {need}°. Tjek om nogle radiatorer står helt åbne.",
           "monthly": "Varmepilot i {month}: ca. {pct} % mindre varme end uden. Rummene var varme til tiden {ontime} % af gangene.",
           "title": "Varmepilot"},
    "en": {"mold": "Mould risk in {room}: {hum} % humidity. Air it out and keep the room warmer.",
           "air": "Stale air in {room} ({co2} ppm CO₂). Open a window for a few minutes.",
           "window": "The window in {room} has been open for {minutes} min. Heating is off meanwhile.",
           "offline": "{device} in {room} isn't responding. Check its battery or connection.",
           "battery": "{device} has {level} % left – change the battery.",
           "not_warming": "{room} isn't getting warm ({temp}° of {want}°). Maybe air in the radiator or a stuck valve.",
           "cooling": "District heating: cooling {today}° today – required is {need}°. Check for radiators fully open.",
           "monthly": "Heat Pilot in {month}: about {pct} % less heat than without. Rooms were warm on time {ontime} % of the time.",
           "title": "Heat Pilot"},
}


def text(a: dict[str, Any], lang: str) -> str:
    t = TEXT.get(lang, TEXT["en"])
    vals = {k: (f"{v:.1f}" if isinstance(v, float) else v) for k, v in a.items()}
    return t[a["kind"]].format(**vals)
