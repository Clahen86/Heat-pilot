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


def bucket(outdoor: float) -> str:
    """The weather a heat-up happened in: below 0, 0-7, 7-13, warmer."""
    return "frost" if outdoor < 0 else "cold" if outdoor < 7 else "cool" if outdoor < 13 else "mild"


class Learning:
    def __init__(self, data_dir: Path) -> None:
        self.file = data_dir / "heat_pilot_learning.json"
        self.s: dict[str, Any] = {"use": {}, "rate": {}, "saved": {}, "ontime": {}, "outdoor": {}}
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
        from . import plan
        day = range(plan.NIGHT_TO, plan.NIGHT_FROM)  # comfort hours are learned in the day - night has its own
        used = {h for h, u in enumerate(got) if u and h in day}
        used |= {h for h in day if h - 1 in used and h + 1 in used}  # a lone empty hour between two used ones stays warm
        return sorted(used)

    def see_outdoor(self, now: datetime, temp: float | None) -> None:
        """The day's average outdoor temperature (for summer)."""
        if temp is None:
            return
        d = self.s.setdefault("outdoor", {}).setdefault(now.date().isoformat(), [0.0, 0])
        d[0] += temp
        d[1] += 1
        for old in sorted(self.s["outdoor"])[:-14]:
            self.s["outdoor"].pop(old, None)

    def outdoor_days(self) -> dict[str, float]:
        return {k: v[0] / v[1] for k, v in (self.s.get("outdoor") or {}).items() if v[1] >= 60}

    # ---------- heating speed ----------

    def see_heating(self, room: str, now: datetime, heating: bool, temp: float | None, target: float | None,
                    heating_type: str, outdoor: float | None = None) -> None:
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
                    if outdoor is not None:  # colder outside, slower to heat: kept by the weather too
                        b = r.setdefault("b", {}).setdefault(bucket(outdoor), {"per_deg": per, "n": 0})
                        b["per_deg"] = round(per if b["n"] == 0 else 0.75 * b["per_deg"] + 0.25 * per, 1)
                        b["n"] += 1
            if not heating or mins > 600 or temp >= ep["target"] - 0.3:
                self._heat.pop(room, None)

    def rate(self, room: str, heating_type: str, outdoor: float | None = None) -> tuple[float, int]:
        r = self.s["rate"].get(room)
        if not r or not r.get("n"):
            return DEFAULT_RATE.get(heating_type, 12.0), 0
        if outdoor is not None and (b := (r.get("b") or {}).get(bucket(outdoor))) and b.get("n", 0) >= 2:
            return b["per_deg"], b["n"]
        return r["per_deg"], r["n"]

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
        ok, seen = sum(x["ok"] for x in ot), sum(x["n"] for x in ot)
        hours_today = max(1.0, now.hour + now.minute / 60)
        n = max(1, len(rooms))
        dh_today = sum(today.values())
        return {"today_dh": round(dh_today, 1), "week_dh": round(dh_week, 1), "days": len(week),
                # In plain words: about how much cooler the rooms were on average, and what that saves.
                "today_avg_down": round(dh_today / (hours_today * n), 1), "today_pct": round(dh_today / (hours_today * n) * 6),
                # Rule of thumb: each degree lower for a day saves about 6 % of the heating that day.
                "week_pct": round(dh_week / (24 * max(1, len(week)) * max(1, len(rooms))) * 6, 1) if week else None,
                "ontime": round(100 * ok / seen) if seen else None, "ontime_n": seen}  # was overwritten by the room count


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


# ---------- the room model, the sun, comfort and strategies (learned, nothing to set up) ----------

def _ema(old: float | None, new: float, a: float) -> float:
    return new if old is None else old + a * (new - old)


class Model:
    """Per room, from what really happens:
    - heat loss: how fast the room cools with the heating off, per degree it is warmer than outside (k, per hour).
      Used to know when setting back is worth it - a room that barely cools over a short gap stays warm instead.
    - the sun: how much each hour of the day warms the room by itself on sunny days (°C per hour) - so heating that
      the sun will do anyway is skipped before it starts.
    - comfort: when people turn a thermostat, the room's comfort moves a little towards it.
    - strategy: each day one way of heating up (normal, early, gentle) is used; the one with the fewest cold
      minutes for the least heating wins - with a day now and then to keep checking."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.s = state.setdefault("model", {"k": {}, "sun": {}, "comfort": {}, "policy": {}})
        for key in ("k", "sun", "comfort", "policy"):
            self.s.setdefault(key, {})
        self._hist: dict[str, list[tuple[datetime, float, bool]]] = {}

    def see(self, room: str, now: datetime, temp: float | None, outdoor: float | None, heating: bool, sunny: bool, sun_up: bool,
            sun: float | None = None) -> None:
        """sun: how sunny this hour is (0..1) when a forecast knows it - the gain is then learned as a clear day's."""
        if temp is None:
            return
        h = self._hist.setdefault(room, [])
        h.append((now, temp, heating))
        while h and (now - h[0][0]).total_seconds() > 3600:
            h.pop(0)
        if len(h) < 20 or (now - h[0][0]).total_seconds() < 1700 or any(x[2] for x in h):
            return
        old = next((x for x in h if (now - x[0]).total_seconds() <= 1900), None)
        if old is None:
            return
        hours = (now - old[0]).total_seconds() / 3600
        rate = (temp - old[1]) / hours  # °C per hour, heating off for the whole half hour
        if not sun_up and outdoor is not None and temp - outdoor >= 5 and rate < 0:
            k = -rate / (temp - outdoor)
            if k < 0.2:
                cur = self.s["k"].get(room)
                self.s["k"][room] = round(_ema(cur, k, 0.1), 4)
        elif sun_up and rate > 0 and (sunny if sun is None else sun >= 0.5):
            slot = str(now.hour)
            g = self.s["sun"].setdefault(room, {})
            g[slot] = round(_ema(g.get(slot), min(rate / (sun or 1.0), 3.0), 0.2), 3)
        if len(h) > 5:
            del h[: len(h) - 5]  # next measurement over a fresh half hour

    def loss(self, room: str) -> float | None:
        return self.s["k"].get(room)

    def drop(self, room: str, temp: float, outdoor: float | None, hours: float) -> float | None:
        """How much the room cools over `hours` with the heating off (None while not learned)."""
        k = self.loss(room)
        if k is None or outdoor is None:
            return None
        import math
        return (temp - outdoor) * (1 - math.exp(-k * hours))

    def sun_gain(self, room: str, start: datetime, hours: float, sun: dict[int, float] | None = None) -> float:
        """The sun's free warming over the coming hours. sun: how sunny each hour will be (sunfeed); without it a
        sunny day is assumed (the caller checks the weather now). An hour the forecast doesn't know counts as grey."""
        from .sunfeed import hour_key
        g = self.s["sun"].get(room) or {}
        total, t = 0.0, start
        while hours > 0:
            step = min(1.0, hours)
            f = 1.0 if sun is None else sun.get(hour_key(t), 0.0)
            total += (g.get(str(t.hour)) or 0.0) * f * step
            t += timedelta(hours=step)
            hours -= step
        return round(total, 2)

    def learn_comfort(self, room: str, temp: float, current: float) -> float:
        new = round(_ema(self.s["comfort"].get(room, current), temp, 0.3), 1)
        self.s["comfort"][room] = new
        return new

    def comfort(self, room: str) -> float | None:
        return self.s["comfort"].get(room)

    # strategies
    ARMS = ("normal", "early", "gentle")

    def arm_today(self, now: datetime) -> str:
        p = self.s["policy"]
        day = now.date().isoformat()
        if p.get("day") != day:
            self._finish(p)
            kind = "weekend" if now.weekday() >= 5 else "workday"
            stats = p.setdefault("stats", {}).setdefault(kind, {})
            import random
            untried = [a for a in self.ARMS if stats.get(a, {}).get("n", 0) < 3]
            if untried:
                arm = untried[0]
            elif random.random() < 0.1:
                arm = random.choice(self.ARMS)
            else:
                arm = min(self.ARMS, key=lambda a: stats[a]["cost"] / stats[a]["n"])
            p.update({"day": day, "kind": kind, "arm": arm, "heat_min": 0, "cold_min": 0})
        return p["arm"]

    def _finish(self, p: dict[str, Any]) -> None:
        if not p.get("day") or not p.get("arm"):
            return
        st = p.setdefault("stats", {}).setdefault(p["kind"], {}).setdefault(p["arm"], {"cost": 0.0, "n": 0})
        st["cost"] += p.get("heat_min", 0) + 30 * p.get("cold_min", 0)  # a cold minute counts like half an hour of heating
        st["n"] += 1

    def see_day(self, heating_rooms: int, cold_rooms: int) -> None:
        p = self.s["policy"]
        p["heat_min"] = p.get("heat_min", 0) + heating_rooms
        p["cold_min"] = p.get("cold_min", 0) + cold_rooms
