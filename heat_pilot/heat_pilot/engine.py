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

from . import brands, discover, plan

_LOGGER = logging.getLogger(__name__)
ROOM_KEYS = {"kind", "heating", "temp_sensor", "comfort", "setback", "night", "away", "day_from", "day_to", "excluded"}


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

    def save(self) -> None:
        self.file.write_text(json.dumps(self.settings, indent=1, ensure_ascii=False))

    # ---------- the house ----------

    async def discover(self) -> None:
        areas = await self.ha.command({"type": "config/area_registry/list"})
        devices = await self.ha.command({"type": "config/device_registry/list"})
        entities = await self.ha.command({"type": "config/entity_registry/list"})
        self.found = discover.find(areas, devices, entities, self.ha.states)
        self.unplaced = discover.unplaced(entities, devices, self.ha.states)
        _LOGGER.info("Found %s rooms with %s thermostats", len(self.found), sum(len(r["thermostats"]) for r in self.found))

    def rooms(self) -> list[dict[str, Any]]:
        """The rooms as found, with the user's own choices on top."""
        out = []
        for r in self.found:
            own = (self.settings.get("rooms") or {}).get(r["area_id"]) or {}
            room = {**r, **{k: v for k, v in own.items() if k in ("kind", "heating", "temp_sensor", "excluded")}}
            room["cfg"] = {**plan.defaults(room), **{k: v for k, v in own.items() if k in ROOM_KEYS - {"kind", "heating", "temp_sensor", "excluded"}}}
            out.append(room)
        return out

    def set_room(self, area: str, values: dict[str, Any]) -> None:
        own = self.settings.setdefault("rooms", {}).setdefault(area, {})
        for k, v in values.items():
            if k in ROOM_KEYS:
                if v is None or v == "":
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
        away = plan.house_away(rooms, st, now, None)
        out = {}
        for r in rooms:
            want = plan.target(r, r["cfg"], st, now, away, None)
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
            out[r["area_id"]] = {"want": want, "temp": self.room_temp(r), "devices": devs, "calls": calls, "same": same,
                                 "mode": self.mode(r["area_id"])}
        self.now = out
        self.away = away

    def status(self) -> dict[str, Any]:
        rooms = []
        for r in self.rooms():
            n = self.now.get(r["area_id"]) or {}
            rooms.append({k: r[k] for k in ("area_id", "name", "kind", "heating", "temp_sensor", "temp_options", "windows",
                                            "presence", "humidity", "excluded") if k in r}
                         | {"cfg": r["cfg"], "thermostats": [{k: t[k] for k in ("entity_id", "name", "brand", "platform", "model")}
                                                             for t in r["thermostats"]]} | n)
        a = self.agree
        return {"rooms": rooms, "unplaced": self.unplaced, "away": getattr(self, "away", False),
                "agree": round(100 * a["same"] / a["checks"]) if a["checks"] else None}
