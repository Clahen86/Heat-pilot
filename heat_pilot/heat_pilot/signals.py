"""Signs from the house beyond motion - kept a minute at a time, per room.

- Someone is in the room: CO2 rising (80 ppm in 10 min), humidity rising (1.5 % in 10 min, not in bathrooms -
  showers), or a light on. People sitting still don't trigger a motion sensor; these keep the room "in use".
- A shower: the bathroom's humidity up 8 % within 15 minutes - kept warm for an hour.
- The sun warms the room: its temperature rising 0.3 °C in half an hour with no heating, the sun up and the weather
  sunny - heating that was about to start waits (free heat).
- Everyone left: an outer door opened, then no movement anywhere for 10 minutes (daytime).
- Turned by hand: a thermostat's setpoint changed by someone else than Heat Pilot - their temperature holds for an
  hour. Heat Pilot's own writes echo back from Zigbee thermostats up to two minutes later, and a thermostat that
  falls back to frost protection (≤ 8 °C, after a restart) is a device fault - neither counts.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any

SUNNY = ("sunny", "partlycloudy", "clear-night")
ECHO_S = 120
FROST_FALLBACK = 8.0
MANUAL_MIN = 60
DOOR_AWAY_MIN = 10


def _num(s: dict[str, Any] | None) -> float | None:
    try:
        return float((s or {}).get("state"))
    except (TypeError, ValueError):
        return None


class Watch:
    def __init__(self) -> None:
        self.hist: dict[str, deque] = {}
        self.shower_until: dict[str, datetime] = {}
        self.sun_until: dict[str, datetime] = {}
        self.door_at: datetime | None = None
        self.last_set: dict[str, float] = {}          # entity -> setpoint seen last minute
        self.ours: dict[str, tuple[float, datetime]] = {}  # entity -> (value, when) Heat Pilot wrote
        self.manual: dict[str, dict[str, Any]] = {}  # room -> {"temp", "until"}

    def see(self, room: dict[str, Any], states: dict[str, Any], now: datetime, heating: bool, temp: float | None) -> None:
        h = self.hist.setdefault(room["area_id"], deque(maxlen=40))
        hum = _num(states.get(room["humidity"][0])) if room.get("humidity") else None
        co2 = _num(states.get(room["co2"][0])) if room.get("co2") else None
        h.append((now, temp, hum, co2, heating))
        if room.get("kind") == "bathroom" and hum is not None:
            old = self._ago(h, 15, 2)
            if old is not None and hum - old >= 8:
                self.shower_until[room["area_id"]] = now + timedelta(minutes=60)

    @staticmethod
    def _ago(h: deque, minutes: int, idx: int) -> float | None:
        """The value of a field about `minutes` ago (the oldest within the window)."""
        if not h:
            return None
        now = h[-1][0]
        vals = [x[idx] for x in h if x[idx] is not None and (now - x[0]).total_seconds() <= minutes * 60]
        return vals[0] if len(vals) >= 2 else None

    def someone(self, room: dict[str, Any], states: dict[str, Any]) -> bool:
        h = self.hist.get(room["area_id"]) or deque()
        if room.get("kind") != "bathroom" and h and h[-1][2] is not None:
            old = self._ago(h, 10, 2)
            if old is not None and h[-1][2] - old >= 1.5:
                return True
        if h and h[-1][3] is not None:
            old = self._ago(h, 10, 3)
            if old is not None and h[-1][3] - old >= 80:
                return True
        return any((states.get(l) or {}).get("state") == "on" for l in room.get("lights") or [])

    def shower(self, area: str, now: datetime) -> bool:
        return now < self.shower_until.get(area, now)

    def sun_warms(self, room: dict[str, Any], states: dict[str, Any], now: datetime) -> bool:
        area = room["area_id"]
        if now < self.sun_until.get(area, now):
            return True
        sun = (states.get("sun.sun") or {}).get("attributes") or {}
        try:
            up = float(sun.get("elevation", 0)) > 5
        except (TypeError, ValueError):
            up = False
        sunny = any((s.get("state") in SUNNY) for e, s in states.items() if e.startswith("weather."))
        h = self.hist.get(area) or deque()
        if not (up and sunny and h) or any(x[4] for x in h if (now - x[0]).total_seconds() <= 1800):
            return False
        old = self._ago(h, 30, 1)
        if old is not None and h[-1][1] is not None and h[-1][1] - old >= 0.3:
            self.sun_until[area] = now + timedelta(minutes=30)
            return True
        return False

    def door_away(self, doors: list[str], states: dict[str, Any], now: datetime, last_motion: datetime | None) -> bool:
        for d in doors:
            s = states.get(d) or {}
            try:
                t = datetime.fromisoformat(s["last_changed"])
            except (KeyError, ValueError, TypeError):
                continue
            if s.get("state") == "on" or (now - t).total_seconds() < 3600:
                self.door_at = max(self.door_at or t, t)
        if self.door_at is None or not 6 <= now.hour < 23:
            return False
        if last_motion is not None and last_motion > self.door_at:
            return False  # someone moved after the door: still home
        return (now - self.door_at).total_seconds() >= DOOR_AWAY_MIN * 60

    # ---------- turned by hand ----------

    def wrote(self, entity: str, value: float, now: datetime) -> None:
        self.ours[entity] = (value, now)

    def see_setpoint(self, area: str, entity: str, setpoint: float | None, now: datetime, controlled: bool) -> None:
        if setpoint is None:
            return
        prev = self.last_set.get(entity)
        self.last_set[entity] = setpoint
        if prev is None or abs(setpoint - prev) < 0.1 or not controlled:
            return  # only where Heat Pilot controls: in shadow, the other system's changes are not "by hand"
        mine = self.ours.get(entity)
        if mine and abs(mine[0] - setpoint) < 0.05 and (now - mine[1]).total_seconds() <= ECHO_S:
            return  # our own write echoing back
        if setpoint <= FROST_FALLBACK:
            return  # the thermostat fell back to frost protection - a fault, put right next round
        self.manual[area] = {"temp": setpoint, "until": now + timedelta(minutes=MANUAL_MIN)}

    def manual_for(self, area: str, now: datetime) -> dict[str, Any] | None:
        m = self.manual.get(area)
        if m and now < m["until"]:
            return m
        self.manual.pop(area, None)
        return None

    def clear_manual(self, area: str) -> None:
        self.manual.pop(area, None)
