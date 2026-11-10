"""The heating pilot: finds the rooms, works out what each should be, and (in shadow) shows what it would send.

Each room starts in shadow: worked out and shown, nothing sent. Control is turned on room by room.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import brands, discover, features, people, plan
from .signals import Watch
from .learning import Learning, seed

_LOGGER = logging.getLogger(__name__)
ROOM_KEYS = {"kind", "heating", "temp_sensor", "comfort", "setback", "night", "away", "day_from", "day_to", "excluded", "fixed_hours", "owner"}


def _num(s: dict[str, Any] | None) -> float | None:
    try:
        return float((s or {}).get("state"))
    except (TypeError, ValueError):
        return None


class Pilot:
    def __init__(self, ha: Any, data_dir: Path) -> None:
        self.ha = ha
        self.file = data_dir / "heat_pilot_settings.json"
        self.settings: dict[str, Any] = {"rooms": {}, "modes": {}}
        try:
            self.settings.update(json.loads(self.file.read_text()))
        except (OSError, ValueError):
            pass
        self.found: list[dict[str, Any]] = []
        self.unplaced: list[str] = []
        self.now: dict[str, dict[str, Any]] = {}
        self.agree = {"same": 0, "checks": 0}
        self.learning = Learning(data_dir)
        self.watch = Watch()
        self.doors: list[str] = []
        self.have: dict[str, bool] = {}
        self.timelines: dict[str, list] = {}

    def save(self) -> None:
        self.file.write_text(json.dumps(self.settings, indent=1, ensure_ascii=False))

    # ---------- the house ----------

    async def discover(self) -> None:
        areas = await self.ha.command({"type": "config/area_registry/list"})
        devices = await self.ha.command({"type": "config/device_registry/list"})
        entities = await self.ha.command({"type": "config/entity_registry/list"})
        self.found = discover.find(areas, devices, entities, self.ha.states)
        self.unplaced = discover.unplaced(entities, devices, self.ha.states)
        self.doors = discover.exit_doors(entities, self.ha.states)
        _LOGGER.info("Found %s rooms with %s thermostats", len(self.found), sum(len(r["thermostats"]) for r in self.found))

    async def seed_history(self) -> None:
        """First start: learn when each room is used from the last 10 days of its motion sensors."""
        from datetime import timedelta

        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        end = datetime.now(tz)
        start = end - timedelta(days=10)
        for r in self.found:
            if self.learning.s["use"].get(r["area_id"]) or not r["presence"]:
                continue
            intervals = []
            for p in r["presence"]:
                try:
                    hist = await self.ha.history(p, start, end)
                except Exception:  # noqa: BLE001
                    continue
                on = None
                for h in (hist[0] if hist else []):
                    t = datetime.fromisoformat(h["last_changed"]).astimezone(tz)
                    if h.get("state") == "on" and on is None:
                        on = t
                    elif h.get("state") != "on" and on is not None:
                        intervals.append((on, t))
                        on = None
                if on is not None:
                    intervals.append((on, end))
            seed(self.learning, r["area_id"], intervals, start, end)
            _LOGGER.info("Learned %s from %s motions", r["name"], len(intervals))
        self.learning.save()

    def rooms(self) -> list[dict[str, Any]]:
        """The rooms as found, with the user's own choices on top."""
        out = []
        for r in self.found:
            own = (self.settings.get("rooms") or {}).get(r["area_id"]) or {}
            room = {**r, **{k: v for k, v in own.items() if k in ("kind", "heating", "temp_sensor", "excluded")}}
            room["cfg"] = {**plan.defaults(room), **{k: v for k, v in own.items() if k in ROOM_KEYS - {"kind", "heating", "temp_sensor", "excluded", "fixed_hours", "owner"}}}
            room["fixed_hours"] = bool(own.get("fixed_hours"))
            # Whose room it is: chosen, or the person it is named after ("" = nobody's).
            room["owner"] = own["owner"] if "owner" in own else people.owner_of(r["name"], people.persons(self.ha.states), self.ha.states)
            out.append(room)
        return out

    def set_room(self, area: str, values: dict[str, Any]) -> None:
        own = self.settings.setdefault("rooms", {}).setdefault(area, {})
        for k, v in values.items():
            if k in ROOM_KEYS:
                if k == "owner":
                    own[k] = v or ""  # "" = nobody's room (also stops the guess)
                elif v is None or v == "":
                    own.pop(k, None)
                else:
                    own[k] = v
        self.save()

    def mode(self, area: str) -> str:
        return (self.settings.get("modes") or {}).get(area, "shadow")

    # ---------- every minute ----------

    def room_temp(self, room: dict[str, Any]) -> float | None:
        st = self.ha.states
        if room.get("temp_sensor") and (t := _num(st.get(room["temp_sensor"]))) is not None:
            return t
        vals = [a.get("current_temperature") for th in room["thermostats"]
                if isinstance(a := (st.get(th["entity_id"]) or {}).get("attributes"), dict) and a.get("current_temperature") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def tick(self) -> None:
        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        now = datetime.now(tz)
        st = self.ha.states
        rooms = [r for r in self.rooms() if not r.get("excluded")]
        ps = people.persons(st)
        self.have = features.found(rooms, st, self.doors, ps)
        on = features.active(self.settings, self.have)
        self.on = on
        last_motion = self._last_motion(rooms, st)
        day = 6 <= now.hour < 23
        motion_away = plan.house_away(rooms, st, now, None) and day and not (on["people"] and not people.all_away(st, ps))
        door_away = on["door"] and day and self.watch.door_away(self.doors, st, now, last_motion)
        # Every phone away - and no movement for half an hour (someone without a tracked phone may be home).
        quiet = last_motion is None or (now - last_motion).total_seconds() >= 1800
        phones_away = on["people"] and people.all_away(st, ps) and quiet
        away = motion_away or door_away or phones_away
        self.away_why = "phones" if phones_away else "door" if door_away else "motion" if motion_away else None
        coming = people.coming_home(st, ps) if on["people"] else []
        self.coming = coming
        outdoor_now = self.outdoor()
        self.learning.see_outdoor(now, outdoor_now)
        outdoor = outdoor_now if on["weather"] else None
        is_summer = on["summer"] and people.summer(self.learning.outdoor_days(), now)
        holiday = people.holiday(st, ps, now, True) if on["holiday"] else None
        self.summer_now, self.holiday_now = is_summer, holiday
        out = {}
        for r in rooms:
            a_id = r["area_id"]
            temp = self.room_temp(r)
            rate, _n = self.learning.rate(a_id, r["heating"], outdoor)
            own_hours = bool((self.settings.get("rooms") or {}).get(a_id, {}).get("fixed_hours"))
            by_day = {d: (None if own_hours else self.learning.hours(a_id, d)) for d in range(7)}
            moving = any((st.get(p) or {}).get("state") == "on" or self._recent_on(st.get(p), now) for p in r["presence"])
            heating_now = any((st.get(th["entity_id"]) or {}).get("attributes", {}).get("hvac_action") == "heating" for th in r["thermostats"])
            self.watch.see(r, st, now, heating_now, temp)
            signs = on["signals"] and self.watch.someone(r, st)
            controlled = self.mode(a_id) == "control"
            for th in r["thermostats"]:
                sp = ((st.get(th["entity_id"]) or {}).get("attributes") or {}).get("temperature")
                self.watch.see_setpoint(a_id, th["entity_id"], float(sp) if isinstance(sp, (int, float)) else None, now,
                                        controlled and on["manual"])
            manual = self.watch.manual_for(a_id, now) if on["manual"] else None
            want = plan.target(r, r["cfg"], st, now, away, manual, by_day[now.weekday()], temp, rate, moving or signs,
                               on["shower"] and self.watch.shower(a_id, now), on["sun"] and self.watch.sun_warms(r, st, now),
                               is_summer, holiday, bool(on["people"] and people.owners_away(st, r.get("owner"))),
                               bool(coming))
            if r["presence"]:
                self.learning.see_presence(a_id, now, moving)
            self.learning.see_heating(a_id, now, heating_now, temp, want["temp"], r["heating"], outdoor)
            self.learning.see_result(a_id, now, temp, want["temp"], r["cfg"]["comfort"], want["why"])
            self.timelines[a_id] = plan.timeline(r, r["cfg"], now, by_day, temp, rate)
            devs, calls, same = [], [], True
            for th in r["thermostats"]:
                s = st.get(th["entity_id"]) or {}
                a = dict(s.get("attributes") or {})
                a["_state"] = s.get("state")
                prof = th["profile"]
                c = brands.off_calls(th["entity_id"], a, prof) if want["temp"] is None else brands.heat_calls(th["entity_id"], a, prof, want["temp"])
                calls += c
                cur_off = s.get("state") == "off"
                cur = a.get("temperature")
                if want["temp"] is None:
                    same = same and (cur_off or (cur is not None and float(cur) <= float(a.get("min_temp") or 5) + 0.1))
                else:
                    # Another system that turns the valve off once the room is warm enough heats to the same.
                    warm = (room_t := self.room_temp(r)) is not None and room_t >= want["temp"] - 0.3
                    same = same and cur is not None and abs(float(cur) - want["temp"]) <= 0.5 and (not cur_off or warm)
                devs.append({"entity_id": th["entity_id"], "name": th["name"], "brand": th["brand"], "state": s.get("state"),
                             "setpoint": cur, "temp": a.get("current_temperature"), "action": a.get("hvac_action")})
            self.agree["checks"] += 1
            self.agree["same"] += int(same)
            out[a_id] = {"want": want, "temp": temp, "devices": devs, "calls": calls, "same": same, "mode": self.mode(a_id),
                         "heating": heating_now, "occupied": moving or signs, "signs": signs, "rate": rate, "rate_n": _n,
                         "learned": self.learning.known(a_id), "hours_today": by_day[now.weekday()]}
        self.now = out
        self.away = away
        if now.minute % 10 == 0:
            self.learning.save()

    @staticmethod
    def _last_motion(rooms: list[dict[str, Any]], st: dict[str, Any]) -> datetime | None:
        latest = None
        for p in (p for r in rooms for p in r.get("presence") or []):
            s = st.get(p) or {}
            try:
                t = datetime.fromisoformat(s["last_changed"])
            except (KeyError, ValueError, TypeError):
                continue
            latest = t if latest is None or t > latest else latest
        return latest

    def set_feature(self, key: str, on: bool) -> None:
        if key in features.FEATURES:
            self.settings.setdefault("features", {})[key] = bool(on)
            self.save()

    @staticmethod
    def _recent_on(s: dict[str, Any] | None, now: datetime) -> bool:
        from .learning import HOLD_MIN
        try:
            return (now - datetime.fromisoformat((s or {})["last_changed"])).total_seconds() < HOLD_MIN * 60 and (s or {}).get("state") == "off"
        except (KeyError, ValueError, TypeError):
            return False

    def status(self) -> dict[str, Any]:
        rooms = []
        for r in self.rooms():
            n = self.now.get(r["area_id"]) or {}
            rooms.append({k: r[k] for k in ("area_id", "name", "kind", "heating", "temp_sensor", "temp_options", "windows",
                                            "presence", "humidity", "excluded", "fixed_hours", "owner") if k in r}
                         | {"cfg": r["cfg"], "thermostats": [{k: t[k] for k in ("entity_id", "name", "brand", "platform", "model")}
                                                             for t in r["thermostats"]]} | n)
        a = self.agree
        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        now = datetime.now(tz)
        for room in rooms:
            room["timeline"] = self.timelines.get(room["area_id"]) or []
        out_t = self.outdoor()
        return {"rooms": rooms, "unplaced": self.unplaced, "away": getattr(self, "away", False), "now": now.isoformat(),
                "agree": round(100 * a["same"] / a["checks"]) if a["checks"] else None, "outdoor": out_t,
                "learning": self.learning.summary(now, [r["area_id"] for r in rooms if not r.get("excluded")]),
                "features": {k: {"found": bool(self.have.get(k)), "on": bool(getattr(self, "on", {}).get(k))}
                             for k in features.FEATURES if self.have.get(k)},
                "doors": self.doors, "persons": [{"entity_id": p, "name": (self.ha.states.get(p) or {}).get("attributes", {}).get("friendly_name") or p,
                                                  "home": people.home(self.ha.states, p)} for p in people.persons(self.ha.states)],
                "away_why": getattr(self, "away_why", None), "coming": getattr(self, "coming", []),
                "summer": getattr(self, "summer_now", False), "holiday": getattr(self, "holiday_now", None)}

    def outdoor_sensor(self) -> str | None:
        """The weather's or an outdoor sensor's temperature - shown beside the house."""
        st = self.ha.states
        for e, s in st.items():
            if e.startswith("weather."):
                return None if (s.get("attributes") or {}).get("temperature") is None else e
        return None

    def outdoor(self) -> float | None:
        e = self.outdoor_sensor()
        try:
            return float(((self.ha.states.get(e or "") or {}).get("attributes") or {}).get("temperature"))
        except (TypeError, ValueError):
            return None
