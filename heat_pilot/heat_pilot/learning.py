"""What Heat Pilot learns by itself - from what really happens in each room.

- When each room is used: every minute, per weekday and hour, whether someone moved in the room. A slot with
  enough days and use more than half the time is a comfort hour; a slot that is mostly empty is set back.
- How fast each room heats: from the moment its thermostats start heating until the room is warm, in minutes per
  degree (a moving average) - so heating starts in time to be warm when the room is used.
- What it saved and whether rooms were warm on time: degree-hours below comfort, and comfort periods that
  started warm.
Kept in a file, so a restart keeps it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

MIN_DAYS = 3        # a slot needs this many days before it's trusted
USED = 0.25         # share of the minutes with someone in the room that makes an hour "used"
DAY = range(6, 22)  # comfort hours are learned in the day only - night has its own temperature (and sleepers)
DEFAULT_RATE = {"radiator": 12.0, "floor": 35.0}  # minutes per degree before anything is learned


class Learning:
    def __init__(self, data_dir: Path) -> None:
        self.file = data_dir / "heat_pilot_learning.json"
        self.s: dict[str, Any] = {"use": {}, "rate": {}, "saved": {}, "ontime": {}}
        try:
            self.s.update(json.loads(self.file.read_text()))
        except (OSError, ValueError):
            pass
        self._heat: dict[str, dict[str, Any]] = {}
        self._minute: dict[str, str] = {}
        self._in_comfort: dict[str, bool] = {}

    def save(self) -> None:
        try:
            self.file.write_text(json.dumps(self.s))
        except OSError:
            pass

    # ---------- use ----------

    def see_presence(self, room: str, now: datetime, moving: bool) -> None:
        """Once a minute: someone in the room or not, in this weekday's hour."""
        key = f"{now.weekday()}_{now.hour}"
        day = now.date().isoformat()
        slot = self.s["use"].setdefault(room, {}).setdefault(key, {"m": 0, "on": 0, "days": [], "p": 0.0})
        slot["m"] += 1
        slot["on"] += int(moving)
        if day not in slot["days"]:
            slot["days"] = (slot["days"] + [day])[-8:]
        if slot["m"] >= 60:  # an hour seen: fold it into the average, weighting recent weeks more
            share = slot["on"] / slot["m"]
            slot["p"] = round(share if len(slot["days"]) <= 1 else 0.7 * slot["p"] + 0.3 * share, 3)
            slot["m"] = slot["on"] = 0

    def used(self, room: str, weekday: int, hour: int) -> bool | None:
        """True/False once learned, None while it isn't yet."""
        use = self.s["use"].get(room) or {}
        slot = use.get(f"{weekday}_{hour}")
        if slot and len(slot.get("days") or []) >= MIN_DAYS:
            return slot["p"] >= USED
        # Not enough of this weekday yet: the same hour on the other workdays (or the weekend) together.
        group = range(5) if weekday < 5 else range(5, 7)
        slots = [use[k] for d in group if (k := f"{d}_{hour}") in use]
        days = sum(len(x.get("days") or []) for x in slots)
        if days < MIN_DAYS:
            return None
        return sum(x["p"] * len(x["days"]) for x in slots) / days >= USED

    def known(self, room: str) -> int:
        """How many hour-slots of the week are learned (of 168)."""
        return sum(1 for d in range(7) for h in range(24) if self.used(room, d, h) is not None)

    def hours(self, room: str, weekday: int) -> list[int] | None:
        """The used hours of a weekday - None while less than half the day is learned."""
        got = [self.used(room, weekday, h) for h in range(24)]
        if sum(x is not None for x in got) < 12:
            return None
        used = {h for h, u in enumerate(got) if u and h in DAY}
        used |= {h for h in DAY if h - 1 in used and h + 1 in used}  # a lone empty hour between two used ones stays warm
        return sorted(used)

    # ---------- heating speed ----------

    def see_heating(self, room: str, now: datetime, heating: bool, temp: float | None, target: float | None,
                    heating_type: str) -> None:
        ep = self._heat.get(room)
        if heating and temp is not None and target is not None and temp < target - 0.5:
            if ep is None or abs(ep["target"] - target) > 0.3:
                self._heat[room] = {"t0": now.isoformat(), "temp0": temp, "target": target}
            return
        if ep and temp is not None:
            mins = (now - datetime.fromisoformat(ep["t0"])).total_seconds() / 60
            rise = temp - ep["temp0"]
            if temp >= ep["target"] - 0.3 and rise >= 0.5 and 5 <= mins <= 600:
                per = mins / rise
                if per <= 120:  # longer: something else was going on (window, sun went away …)
                    r = self.s["rate"].setdefault(room, {"per_deg": DEFAULT_RATE.get(heating_type, 12.0), "n": 0})
                    r["per_deg"] = round(per if r["n"] == 0 else 0.75 * r["per_deg"] + 0.25 * per, 1)
                    r["n"] += 1
            if not heating or mins > 600 or temp >= ep["target"] - 0.3:
                self._heat.pop(room, None)

    def rate(self, room: str, heating_type: str) -> tuple[float, int]:
        r = self.s["rate"].get(room)
        return (r["per_deg"], r["n"]) if r and r.get("n") else (DEFAULT_RATE.get(heating_type, 12.0), 0)

    # ---------- what it gave ----------

    def see_result(self, room: str, now: datetime, temp: float | None, want: float | None, comfort: float, why: str) -> None:
        """Once a minute: degree-minutes below comfort (saved), and whether a comfort period began warm."""
        day = now.date().isoformat()
        sv = self.s["saved"].setdefault(day, {})
        if want is not None and want < comfort:
            sv[room] = round(sv.get(room, 0.0) + (comfort - want) / 60, 3)  # degree-hours
        elif want is None:
            sv[room] = round(sv.get(room, 0.0) + max(0.0, comfort - 12) / 60, 3)  # off (window): counted as down to 12°
        was = self._in_comfort.get(room)
        now_c = why in ("comfort", "manual", "preheat")
        if now_c and was is False and temp is not None and want is not None:  # not on the first minute after a start
            ot = self.s["ontime"].setdefault(room, {"ok": 0, "n": 0})
            ot["n"] += 1
            ot["ok"] += int(temp >= want - 0.5)
        self._in_comfort[room] = now_c
        for old in sorted(self.s["saved"])[:-60]:
            self.s["saved"].pop(old, None)

    def summary(self, now: datetime, rooms: list[str]) -> dict[str, Any]:
        days = sorted(self.s["saved"])
        today = self.s["saved"].get(now.date().isoformat()) or {}
        week = days[-7:]
        dh_week = sum(sum(self.s["saved"][d].values()) for d in week)
        ot = [self.s["ontime"].get(r) for r in rooms if self.s["ontime"].get(r)]
        ok, n = sum(x["ok"] for x in ot), sum(x["n"] for x in ot)
        return {"today_dh": round(sum(today.values()), 1), "week_dh": round(dh_week, 1), "days": len(week),
                # Rule of thumb: each degree lower for a day saves about 6 % of the heating that day.
                "week_pct": round(dh_week / (24 * max(1, len(week)) * max(1, len(rooms))) * 6, 1) if week else None,
                "ontime": round(100 * ok / n) if n else None, "ontime_n": n}


HOLD_MIN = 10  # a motion sensor's "on" counts as someone in the room for this long after it


def occupied_minutes(intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> set[int]:
    """The minutes (as minute numbers since start) with someone in the room - each motion held HOLD_MIN minutes."""
    out: set[int] = set()
    for a, b in intervals:
        a, b = max(a, start), min(b + timedelta(minutes=HOLD_MIN), end)
        m0, m1 = int((a - start).total_seconds() // 60), int((b - start).total_seconds() // 60)
        out.update(range(max(0, m0), max(m0, m1) + 1))
    return out


def seed(learning: Learning, room: str, intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> None:
    """Learn at once from the recorder's history of the room's motion sensors (about 10 days)."""
    occ = occupied_minutes(intervals, start, end)
    slots: dict[str, dict[str, Any]] = {}
    t = start.replace(minute=0, second=0, microsecond=0)
    if t < start:
        t += timedelta(hours=1)
    while t + timedelta(hours=1) <= end:
        m0 = int((t - start).total_seconds() // 60)
        share = sum(1 for m in range(m0, m0 + 60) if m in occ) / 60
        s = slots.setdefault(f"{t.weekday()}_{t.hour}", {"shares": [], "days": []})
        s["shares"].append(share)
        s["days"].append(t.date().isoformat())
        t += timedelta(hours=1)
    use = learning.s["use"].setdefault(room, {})
    for key, s in slots.items():
        p = 0.0
        for i, sh in enumerate(s["shares"]):
            p = sh if i == 0 else 0.7 * p + 0.3 * sh
        use[key] = {"m": 0, "on": 0, "days": s["days"][-8:], "p": round(p, 3)}
