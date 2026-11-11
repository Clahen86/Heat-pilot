"""The heating pilot: finds the rooms, works out what each should be, and (in shadow) shows what it would send.

Each room starts in shadow: worked out and shown, nothing sent. Control is turned on room by room.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import alerts, brands, discover, features, people, plan, pricefeed, sunfeed, supply, ventilation
from .signals import Watch
from .control import Sender, exercise_now
from .learning import Learning, Model, seed

_LOGGER = logging.getLogger(__name__)
ROOM_KEYS = {"doors_extra", "evening", "evening_from", "evening_to", "price_flex", "kind", "heating", "temp_sensor", "comfort", "setback", "night", "away", "day_from", "day_to", "excluded", "fixed_hours", "owner"}


def f_to_c(v: float) -> float:
    return (v - 32) * 5 / 9


def c_to_f(v: float) -> float:
    return v * 9 / 5 + 32


def floor_level(name: str) -> int:
    """A floor without a level set: guessed from its name (basement below, ground floor, upstairs, attic)."""
    import re
    n = name.lower()
    if re.search(r"kælder|kaelder|basement|cellar|keller|källare|kjeller|sous-sol|kelder", n):
        return -1
    if re.search(r"loft|attic|dachboden|vind|grenier|zolder", n):
        return 2
    if re.search(r"1\.? ?sal|first|upstairs|ober|övervåning|overetasje|étage|eerste|1st|2\.? ?etage", n):
        return 1
    return 0


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
        self.floors: list[dict[str, Any]] = []
        self.unplaced: list[str] = []
        self.now: dict[str, dict[str, Any]] = {}
        self.agree = {"same": 0, "checks": 0}
        self.learning = Learning(data_dir)
        self.watch = Watch()
        self.doors: list[str] = []
        self.all_doors: list[str] = []
        self.have: dict[str, bool] = {}
        self.meter: dict[str, str] | None = None
        self.price_entity: str | None = None
        self.vent: dict[str, Any] | None = None
        self.vent_now: dict[str, Any] | None = None
        self.cooling_options: list[str] = []
        self.alerts = alerts.Alerts(self.learning.s)
        self.model = Model(self.learning.s)
        self.sender = Sender()
        self.forecast: list[tuple[datetime, float, str]] = []
        self.clouds: dict[int, float] = {}       # cloud cover % per hour (weather forecast)
        self.energy_pv: dict[int, float] = {}    # kWh per hour from the Energy dashboard's solar forecast
        self.sunfeed = sunfeed.SunFeed(self.learning.s)
        self.sun_hours: dict[int, float] = {}
        self.notify: list[str] = []
        self.cooling = supply.Cooling(self.learning.s)
        self.timelines: dict[str, list] = {}

    def save(self) -> None:
        self.file.write_text(json.dumps(self.settings, indent=1, ensure_ascii=False))

    # ---------- units: everything is worked out in °C; homes in °F are read and written in °F ----------

    @property
    def fahrenheit(self) -> bool:
        return "F" in str((self.ha.config.get("unit_system") or {}).get("temperature") or "")

    def c(self, v: Any, unit: str | None = None) -> float | None:
        """A temperature from Home Assistant in °C (a sensor's own unit, or the home's for climate and weather)."""
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        u = unit if unit is not None else ("°F" if self.fahrenheit else "°C")
        return round(f_to_c(x), 2) if "F" in str(u) else x

    def out_unit(self, v: float) -> float:
        """A temperature to send to a thermostat, in the home's unit."""
        return round(c_to_f(v), 1) if self.fahrenheit else v

    def sensor_c(self, entity: str | None) -> float | None:
        s = self.ha.states.get(entity or "") or {}
        return self.c(s.get("state"), (s.get("attributes") or {}).get("unit_of_measurement") or "°C")

    # ---------- the house ----------

    async def discover(self) -> None:
        areas = await self.ha.command({"type": "config/area_registry/list"})
        devices = await self.ha.command({"type": "config/device_registry/list"})
        entities = await self.ha.command({"type": "config/entity_registry/list"})
        self.found = discover.find(areas, devices, entities, self.ha.states)
        try:
            floors = await self.ha.command({"type": "config/floor_registry/list"})
        except Exception:  # noqa: BLE001 - older Home Assistant: no floors
            floors = []
        self.floors = sorted(({"floor_id": f["floor_id"], "name": f.get("name"),
                               "level": f.get("level") if f.get("level") is not None else floor_level(f.get("name") or "")} for f in floors),
                             key=lambda f: -f["level"])
        self.unplaced = discover.unplaced(entities, devices, self.ha.states)
        self.doors = discover.exit_doors(entities, self.ha.states)
        self.all_doors = discover.all_doors(entities, self.ha.states)
        self.meter = supply.find_heat_meter(entities, devices, self.ha.states)
        self.vent = ventilation.find(entities, devices, self.ha.states)
        try:
            svc = await self.ha.command({"type": "get_services"})
            names = sorted((svc.get("notify") or {}).keys())
            self.notify = [n for n in names if n.startswith("mobile_app_")] + [n for n in names if not n.startswith("mobile_app_") and n not in ("notify", "send_message", "persistent_notification")]
        except Exception:  # noqa: BLE001
            self.notify = []
        self.cooling_options = sorted(e for e, s in self.ha.states.items() if e.split(".")[0] in ("binary_sensor", "switch", "input_boolean", "sensor")
                                      and (any(k in (s.get("attributes") or {}) for k in ("precool", "cooling", "free_cooling"))
                                           or any(w in e for w in ("precool", "free_cooling", "frikoling", "natkoling", "kole_mode", "cooling_mode"))))[:30]
        self.price_entity = supply.find_price(entities, self.ha.states, ZoneInfo(self.ha.config.get("time_zone") or "UTC"))
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
            room["cfg"] = {**plan.defaults(room), **{k: v for k, v in own.items() if k in ROOM_KEYS - {"kind", "heating", "temp_sensor", "excluded", "fixed_hours", "owner", "doors_extra"}}}
            if "comfort" not in own and (learned := self.model.comfort(r["area_id"])) is not None:
                room["cfg"]["comfort"] = learned
                room["comfort_learned"] = True
            room["fixed_hours"] = bool(own.get("fixed_hours"))
            room["doors_extra"] = list(own.get("doors_extra") or [])
            room["doors"] = sorted(set(r.get("doors") or []) | set(room["doors_extra"]))
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
        """shadow (the start for every room), control or off."""
        return (self.settings.get("modes") or {}).get(area, "shadow")

    def set_mode(self, area: str | None, mode: str) -> None:
        if mode not in ("shadow", "control", "off"):
            return
        modes = self.settings.setdefault("modes", {})
        if area == "*":  # the whole house at once (every room found)
            for r in self.found:
                modes[r["area_id"]] = mode
            self.save()
            return
        if area is None:  # every room back to shadow
            for a in list(modes):
                modes[a] = "shadow"
        else:
            modes[area] = mode
        self.save()

    async def control(self) -> None:
        """Send what the rooms in control need (nothing at all while every room is in shadow)."""
        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        now = datetime.now(tz)
        rooms = {r["area_id"]: r for r in self.rooms() if not r.get("excluded")}
        todo = []
        for a_id, n in self.now.items():
            r = rooms.get(a_id)
            if not r or self.mode(a_id) != "control":
                continue
            calls = list(n.get("calls") or [])
            if exercise_now(now, getattr(self, "summer_now", False)):
                calls = []
                for th in r["thermostats"]:
                    attrs = dict((self.ha.states.get(th["entity_id"]) or {}).get("attributes") or {})
                    attrs["_state"] = (self.ha.states.get(th["entity_id"]) or {}).get("state")
                    calls += brands.heat_calls(th["entity_id"], attrs, th["profile"], float(attrs.get("max_temp") or 30))
            gaps = {th["entity_id"]: float(th["profile"].get("min_gap_min") or 1) for th in r["thermostats"]}
            steps = {th["entity_id"]: float(((self.ha.states.get(th["entity_id"]) or {}).get("attributes") or {}).get("target_temp_step") or 0.5)
                     for th in r["thermostats"]}
            todo += self.sender.due(calls, self.ha.states, gaps, now, steps)
        if todo:
            await self.sender.send(self.ha, todo, now, lambda e, v, t: self.watch.wrote(e, self.c(v) or v, t))

    # ---------- every minute ----------

    def room_temp(self, room: dict[str, Any]) -> float | None:
        st = self.ha.states
        if room.get("temp_sensor") and (t := self.sensor_c(room["temp_sensor"])) is not None:
            return t
        vals = [self.c(a.get("current_temperature")) for th in room["thermostats"]
                if isinstance(a := (st.get(th["entity_id"]) or {}).get("attributes"), dict) and a.get("current_temperature") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def tick(self) -> None:
        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        now = datetime.now(tz)
        st = self.ha.states
        rooms = [r for r in self.rooms() if not r.get("excluded")]
        features.apply_tune(self.settings)
        ps = people.persons(st)
        self.have = features.found(rooms, st, self.doors, ps, self.meter, self.price_entity, self.vent)
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
        dh = self.settings.get("district") or {}
        need = float(dh.get("need", 25.0))
        self.cooling_now = self.cooling.see(self.meter, st, now) if on["district"] else None
        self.cooling_info = self.cooling.summary(now, need, dh.get("penalty"), dh.get("bonus")) if on["district"] else None
        spread = on["district"] and supply.poor_cooling(self.cooling_info, need)
        level = None
        if on["price"]:
            prices, _ = pricefeed.collect(st, self.price_entity, [], tz)
            level = supply.price_level(prices, now)
        self.price_level = level
        sun_attr = (st.get("sun.sun") or {}).get("attributes") or {}
        try:
            sun_up = float(sun_attr.get("elevation", 0)) > 5
        except (TypeError, ValueError):
            sun_up = False
        sunny = any(v.get("state") in ("sunny", "partlycloudy") for e, v in st.items() if e.startswith("weather."))
        conditions = {sunfeed.hour_key(w): c for w, _t, c in self.forecast}
        self.sun_hours = self.sunfeed.factors(st, self.energy_pv, self.clouds, conditions, now)
        sun_now = self.sun_hours.get(sunfeed.hour_key(now)) if self.sun_hours else None
        arm = self.model.arm_today(now) if on["strategy"] else "normal"
        self.arm = arm
        cold_snap = on["weather"] and outdoor_now is not None and any(
            t <= outdoor_now - 8 for when, t, _c in self.forecast if now <= when <= now + timedelta(hours=48))
        self.cold_snap = cold_snap
        occupied_floors = {r.get("floor_id") for r in rooms if r.get("floor_id") and (
            any((st.get(p) or {}).get("state") == "on" or self._recent_on(st.get(p), now) for p in r["presence"]))}
        radiators_heating = any((self.now.get(r["area_id"]) or {}).get("heating") for r in rooms if r.get("heating") != "floor")
        cooling = ventilation.other_cooling(st, (self.settings.get("ventilation") or {}).get("cooling_entity"))
        self.vent_now = None
        if on["ventilation"] and self.vent:
            temps = [t for r in rooms if (t := self.room_temp(r)) is not None]
            comforts = [r["cfg"]["comfort"] for r in rooms]
            shower = on["shower"] and any(self.watch.shower(r["area_id"], now) for r in rooms)
            want_v = ventilation.decide(rooms, st, shower, away, sum(temps) / len(temps) if temps else None,
                                        sum(comforts) / len(comforts) if comforts else 21.0, outdoor_now)
            cur = ventilation.current_level(self.vent, st)
            self.vent_now = {**want_v, "current": cur, "same": cur == want_v["level"], "efficiency": ventilation.efficiency(self.vent, st),
                             "bypass": ventilation.bypass_open(self.vent, st), "calls": ventilation.calls(self.vent, st, want_v["level"]),
                             "temps": {k: self.sensor_c(self.vent.get(k)) for k in ("outdoor", "supply", "extract", "exhaust")},
                             "name": self.vent["name"], "model": self.vent.get("model")}
            cooling = cooling or want_v["cooling"]
        self.cooling_flag = cooling
        out = {}
        heat_n = cold_n = 0
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
                self.watch.see_setpoint(a_id, th["entity_id"], self.c(sp) if isinstance(sp, (int, float)) else None, now,
                                        controlled and on["manual"])
            manual = self.watch.manual_for(a_id, now) if on["manual"] else None
            hours_today = by_day[now.weekday()]
            self.model.see(a_id, now, temp, outdoor_now, heating_now, sunny, sun_up, sun_now)
            nxt = plan.next_comfort({**plan.defaults(r), **r["cfg"]}, hours_today, now)
            gap_h = (nxt - now).total_seconds() / 3600 if nxt else None
            drop = self.model.drop(a_id, temp, outdoor_now, gap_h) if (temp is not None and gap_h is not None and gap_h <= 3) else None
            today = now.date().isoformat()
            seen_today = any(((st.get(p) or {}).get("last_changed") or "")[:10] == today or (st.get(p) or {}).get("state") == "on" for p in r["presence"])
            extra = {
                "door": on["doors"] and any((st.get(d) or {}).get("state") == "on" and not self._recent_on_since(st.get(d), now, 10) for d in r.get("doors") or []),
                "noshow": bool(r["presence"]) and now.hour >= 12 and not seen_today,
                "sun_ahead": (self.model.sun_gain(a_id, now, gap_h, self.sun_hours) if self.sun_hours
                              else self.model.sun_gain(a_id, now, gap_h) if sunny else 0.0) if (on["sun"] and gap_h) else 0.0,
                "arm": arm, "cold_snap": cold_snap,
                "floor_active": on["floor"] and r.get("floor_id") in occupied_floors,
                "buffer": on["floor"] and on["district"] and radiators_heating and supply.poor_cooling(getattr(self, "cooling_info", None), float((self.settings.get("district") or {}).get("need", 25.0))),
                "hold_warm": drop is not None and drop < 0.5,
            }
            want = plan.target(r, r["cfg"], st, now, away, manual, hours_today, temp, rate, moving or signs,
                               on["shower"] and self.watch.shower(a_id, now), on["sun"] and self.watch.sun_warms(r, st, now),
                               is_summer, holiday, bool(on["people"] and people.owners_away(st, r.get("owner"))),
                               bool(coming), level if supply.is_electric(r) else None, spread, cooling, extra)
            if manual and r["cfg"].get("comfort") and plan.NIGHT_TO <= now.hour < plan.NIGHT_FROM and not self.watch.manual.get(a_id, {}).get("learned"):
                self.model.learn_comfort(a_id, manual["temp"], r["cfg"]["comfort"])  # turned by hand: comfort moves a little
                self.watch.manual[a_id]["learned"] = True
            if want["temp"] is not None and temp is not None:
                cold_n += int(want["why"] in ("comfort", "comfort_evening", "occupied") and temp < want["temp"] - 0.5)
            heat_n += int(heating_now)
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
                c = brands.off_calls(th["entity_id"], a, prof) if want["temp"] is None else brands.heat_calls(th["entity_id"], a, prof, self.out_unit(want["temp"]))
                calls += c
                cur_off = s.get("state") == "off"
                cur = self.c(a.get("temperature"))
                if want["temp"] is None:
                    same = same and (cur_off or (cur is not None and cur <= (self.c(a.get("min_temp")) or 5) + 0.1))
                else:
                    # Another system that turns the valve off once the room is warm enough heats to the same.
                    warm = (room_t := self.room_temp(r)) is not None and room_t >= want["temp"] - 0.3
                    same = same and cur is not None and abs(cur - want["temp"]) <= 0.5 and (not cur_off or warm)
                devs.append({"entity_id": th["entity_id"], "name": th["name"], "brand": th["brand"], "state": s.get("state"),
                             "setpoint": cur, "temp": self.c(a.get("current_temperature")), "action": a.get("hvac_action")})
            self.agree["checks"] += 1
            self.agree["same"] += int(same)
            out[a_id] = {"want": want, "temp": temp, "devices": devs, "calls": calls, "same": same, "mode": self.mode(a_id),
                         "heating": heating_now, "occupied": moving or signs, "signs": signs, "rate": rate, "rate_n": _n,
                         "learned": self.learning.known(a_id), "hours_today": by_day[now.weekday()],
                         "loss": self.model.loss(a_id), "sun_gain": self.model.s["sun"].get(a_id), "extra": {k: v for k, v in extra.items() if v}}
        self.now = out
        self.away = away
        self.alerts.check(rooms, out, st, now, outdoor_now, getattr(self, "cooling_info", None))
        if on["strategy"]:
            self.model.see_day(heat_n, cold_n)
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

    def lang(self) -> str:
        code = str(self.ha.config.get("language") or "en")[:2]
        code = "nb" if code in ("no", "nn") else code
        return code if code in ("da", "en", "de", "fr", "nl", "sv", "nb") else "en"

    SENTENCE = {
        "da": ("Sommer – varmen er slukket.", "Ferie – huset holdes køligt.", "Alle er ude – huset er sænket", "Vindue åbent i {r}",
               "{n} rum varmer", "{r} varmer", "{n} rum er sænket", "Alle rum har den rette temperatur."),
        "en": ("Summer – heating is off.", "Holiday – the house is kept cool.", "Everyone is away – the house is turned down", "Window open in {r}",
               "{n} rooms heating", "{r} is heating", "{n} rooms turned down", "Every room is as it should be."),
        "de": ("Sommer – die Heizung ist aus.", "Urlaub – das Haus bleibt kühl.", "Alle sind weg – das Haus ist abgesenkt", "Fenster offen in {r}",
               "{n} Räume heizen", "{r} heizt", "{n} Räume abgesenkt", "Jeder Raum hat die richtige Temperatur."),
        "fr": ("Été – le chauffage est coupé.", "Vacances – la maison reste fraîche.", "Tout le monde est absent – la maison est baissée", "Fenêtre ouverte : {r}",
               "{n} pièces chauffent", "{r} chauffe", "{n} pièces baissées", "Chaque pièce est à la bonne température."),
        "nl": ("Zomer – de verwarming is uit.", "Vakantie – het huis blijft koel.", "Iedereen is weg – het huis is verlaagd", "Raam open in {r}",
               "{n} kamers verwarmen", "{r} verwarmt", "{n} kamers verlaagd", "Elke kamer heeft de juiste temperatuur."),
        "sv": ("Sommar – värmen är avstängd.", "Semester – huset hålls svalt.", "Alla är borta – huset är sänkt", "Fönster öppet i {r}",
               "{n} rum värms", "{r} värms", "{n} rum sänkta", "Alla rum har rätt temperatur."),
        "nb": ("Sommer – varmen er av.", "Ferie – huset holdes kjølig.", "Alle er borte – huset er senket", "Vindu åpent i {r}",
               "{n} rom varmes", "{r} varmes", "{n} rom senket", "Alle rom har riktig temperatur."),
    }

    def sentence(self) -> str:
        """One sentence of what is going on - for the dashboard card and the sensor."""
        t = self.SENTENCE[self.lang()]
        rooms = {r["area_id"]: r for r in self.rooms()}
        whys = [(rooms[a]["name"], (n.get("want") or {}).get("why"), n.get("heating")) for a, n in self.now.items() if a in rooms]
        if getattr(self, "summer_now", False):
            return t[0]
        if getattr(self, "holiday_now", None):
            return t[1]
        parts = []
        if getattr(self, "away", False):
            parts.append(t[2])
        heat = [n for n, w, h in whys if h]
        down = [n for n, w, h in whys if w in ("setback", "owner_away")]
        win = [n for n, w, h in whys if w == "window"]
        if win:
            parts.append(t[3].replace("{r}", win[0]))
        if heat:
            parts.append(t[4].replace("{n}", str(len(heat))) if len(heat) > 1 else t[5].replace("{r}", heat[0]))
        if down:
            parts.append(t[6].replace("{n}", str(len(down))))
        return (". ".join(parts) + ".") if parts else t[7]

    def month_report(self, now: datetime) -> dict[str, Any] | None:
        """Last month: degrees turned down, about how much heat that saved, warm on time, district cooling."""
        first = now.replace(day=1)
        last_month = (first - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")
        days = [d for d in self.learning.s["saved"] if d.startswith(last_month)]
        if not days:
            return None
        rooms = [r for r in self.rooms() if not r.get("excluded")]
        dh = sum(sum(self.learning.s["saved"][d].values()) for d in days)
        pct = round(dh / (24 * len(days) * max(1, len(rooms))) * 6, 1)
        cool = self.cooling.period(sorted(d for d in self.cooling.s if d.startswith(last_month))) if self.meter else None
        return {"month": last_month, "days": len(days), "degree_hours": round(dh), "pct": pct, "cooling": cool,
                "ontime": self.learning.summary(now, [r["area_id"] for r in rooms]).get("ontime")}

    async def send_alerts(self) -> None:
        """Messages for the warnings due now - only to the phones chosen."""
        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        now = datetime.now(tz)
        due = self.alerts.to_send(self.settings, now)
        lang = self.lang()
        m = self.settings.get("messages") or {}
        if now.day == 1 and now.hour >= 9 and (m.get("kinds") or {}).get("monthly", True) and m.get("targets") \
                and self.alerts.s["sent"].get("monthly") != now.strftime("%Y-%m") and (rep := self.month_report(now)):
            self.alerts.s["sent"]["monthly"] = now.strftime("%Y-%m")
            due.append({"kind": "monthly", **rep})
        for a in due:
            for target in (self.settings.get("messages") or {}).get("targets") or []:
                try:
                    await self.ha.call_service("notify", target, {"title": alerts.TEXT[lang]["title"], "message": alerts.text(a, lang)})
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("Could not send to notify.%s", target)

    def set_messages(self, values: dict[str, Any]) -> None:
        m = self.settings.setdefault("messages", {})
        if "targets" in values:
            m["targets"] = [str(t) for t in values["targets"] or [] if str(t) in self.notify]
        if "night" in values:
            m["night"] = bool(values["night"])
        if "kind" in values:
            m.setdefault("kinds", {})[str(values["kind"])] = bool(values.get("on"))
        self.save()

    async def publish(self) -> None:
        """For Energy Pilot (and dashboards): the electric heating now and the hours it plans to heat - only when
        some rooms are heated by electricity."""
        rooms = [r for r in self.rooms() if not r.get("excluded") and supply.is_electric(r)]
        if not rooms:
            return
        heating = [r["name"] for r in rooms if (self.now.get(r["area_id"]) or {}).get("heating")]
        planned = sorted({q["t"] for r in rooms for q in self.timelines.get(r["area_id"]) or []
                          if q["why"] in ("comfort", "preheat", "cheap")})
        try:
            await self.ha.set_state("sensor.varmepilot_elvarme", len(heating),
                                    {"friendly_name": "Varmepilot elvarme", "rooms_heating": heating, "planned": planned[:96],
                                     "price_level": getattr(self, "price_level", None), "icon": "mdi:radiator"})
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not publish", exc_info=True)

    def set_district(self, values: dict[str, Any]) -> None:
        d = self.settings.setdefault("district", {})
        for k in ("need", "penalty", "bonus"):
            if k in values:
                if values[k] in (None, ""):
                    d.pop(k, None)
                else:
                    d[k] = float(values[k])
        self.save()

    def set_ventilation(self, values: dict[str, Any]) -> None:
        v = self.settings.setdefault("ventilation", {})
        if "cooling_entity" in values:
            if values["cooling_entity"]:
                v["cooling_entity"] = str(values["cooling_entity"])
            else:
                v.pop("cooling_entity", None)
        self.save()

    def set_tune(self, key: str, value: Any) -> None:
        spec = features.TUNE.get(key)
        if spec and value in spec[3]:
            self.settings.setdefault("tune", {})[key] = value
            self.save()

    def set_feature(self, key: str, on: bool) -> None:
        if key in features.FEATURES:
            self.settings.setdefault("features", {})[key] = bool(on)
            self.save()

    @staticmethod
    def _recent_on_since(s: dict[str, Any] | None, now: datetime, minutes: float) -> bool:
        """True while the state changed less than `minutes` ago."""
        try:
            return (now - datetime.fromisoformat((s or {})["last_changed"])).total_seconds() < minutes * 60
        except (KeyError, ValueError, TypeError):
            return False

    async def refresh_forecast(self) -> None:
        """The weather's hourly forecast (for a cold snap coming)."""
        w = next((e for e in self.ha.states if e.startswith("weather.")), None)
        if not w:
            return
        try:
            res = await self.ha.call_service("weather", "get_forecasts", {"entity_id": w, "type": "hourly"}, response=True)
            fc = ((res or {}).get("response") or {}).get(w, {}).get("forecast") or []
            self.forecast = [(datetime.fromisoformat(f["datetime"]), float(f["temperature"]), f.get("condition") or "")
                             for f in fc if f.get("temperature") is not None]
            clouds = {}
            for f in fc:
                try:
                    clouds[sunfeed.hour_key(datetime.fromisoformat(f["datetime"]))] = float(f["cloud_coverage"])
                except (KeyError, TypeError, ValueError):
                    continue
            self.clouds = clouds
        except Exception:  # noqa: BLE001
            _LOGGER.debug("No forecast", exc_info=True)
        await self.refresh_energy_pv()

    async def refresh_energy_pv(self) -> None:
        """The solar forecast set up in Home Assistant's Energy dashboard (Forecast.Solar and others), hour by hour."""
        try:
            prefs = await self.ha.command({"type": "energy/get_prefs"})
            ids = [i for src in (prefs or {}).get("energy_sources") or [] if src.get("type") == "solar"
                   for i in src.get("config_entry_solar_forecast") or []]
            fc = await self.ha.command({"type": "energy/solar_forecast"}) if ids else None
            self.energy_pv = sunfeed.pv_from_energy(fc, ids)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("No Energy dashboard solar forecast", exc_info=True)

    def sky(self) -> dict[str, Any]:
        """What the front page draws above the house: the sun's place, the weather and how cloudy it is now."""
        st = self.ha.states
        sun = (st.get("sun.sun") or {}).get("attributes") or {}
        w = next((v for e, v in sorted(st.items()) if e.startswith("weather.")), None) or {}
        cloud = (w.get("attributes") or {}).get("cloud_coverage")
        f = self.sun_hours.get(sunfeed.hour_key(datetime.now())) if self.sun_hours else None
        if f is not None:
            cloud = round((1 - f) * 100)
        return {"elevation": sun.get("elevation"), "azimuth": sun.get("azimuth"), "condition": w.get("state"), "cloud": cloud}

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
                                            "presence", "humidity", "excluded", "fixed_hours", "owner", "floor_id", "doors", "doors_extra", "comfort_learned") if k in r}
                         | {"heat_type": r["heating"], "cfg": r["cfg"],
                            "temp_names": {e: ((self.ha.states.get(e) or {}).get("attributes") or {}).get("friendly_name") or e for e in r.get("temp_options") or []}, "thermostats": [{k: t[k] for k in ("entity_id", "name", "brand", "platform", "model")}
                                                             for t in r["thermostats"]]} | n)
        a = self.agree
        tz = ZoneInfo(self.ha.config.get("time_zone") or "UTC")
        now = datetime.now(tz)
        for room in rooms:
            room["timeline"] = self.timelines.get(room["area_id"]) or []
        out_t = self.outdoor()
        sun = (self.ha.states.get("sun.sun") or {}).get("state")
        return {"unit": "°F" if self.fahrenheit else "°C", "sent": self.sender.log[:20], "setup_done": bool(self.settings.get("setup_done")), "all_doors": [{"entity_id": e, "name": (self.ha.states.get(e) or {}).get("attributes", {}).get("friendly_name") or e} for e in self.all_doors],
                "arm": getattr(self, "arm", None), "cold_snap": getattr(self, "cold_snap", False), "tune": features.tune_view(self.settings), "month": self.month_report(now), "floors": self.floors, "sun": sun, "sun_source": self.sunfeed.source, "sky": self.sky(), "rooms": rooms, "unplaced": self.unplaced, "away": getattr(self, "away", False), "now": now.isoformat(),
                "agree": round(100 * a["same"] / a["checks"]) if a["checks"] else None, "outdoor": out_t,
                "learning": self.learning.summary(now, [r["area_id"] for r in rooms if not r.get("excluded")]),
                "features": {k: {"found": bool(self.have.get(k)), "on": bool(getattr(self, "on", {}).get(k))}
                             for k in features.FEATURES if self.have.get(k)},
                "doors": self.doors, "persons": [{"entity_id": p, "name": (self.ha.states.get(p) or {}).get("attributes", {}).get("friendly_name") or p,
                                                  "home": people.home(self.ha.states, p)} for p in people.persons(self.ha.states)],
                "away_why": getattr(self, "away_why", None), "coming": getattr(self, "coming", []),
                "summer": getattr(self, "summer_now", False), "holiday": getattr(self, "holiday_now", None),
                "cooling": getattr(self, "cooling_info", None), "cooling_now": getattr(self, "cooling_now", None),
                "district": self.settings.get("district") or {}, "price_level": getattr(self, "price_level", None),
                "electric": [r["area_id"] for r in rooms if supply.is_electric(r)],
                "alerts": [{**a, "text": alerts.text(a, self.lang())}
                           for a in self.alerts.active],
                "messages": self.settings.get("messages") or {}, "notify": self.notify, "alert_kinds": alerts.KINDS,
                "vent": getattr(self, "vent_now", None), "ventilation": self.settings.get("ventilation") or {},
                "cooling_options": [{"entity_id": e, "name": (self.ha.states.get(e) or {}).get("attributes", {}).get("friendly_name") or e} for e in self.cooling_options]}

    def outdoor_sensor(self) -> str | None:
        """The weather's or an outdoor sensor's temperature - shown beside the house."""
        st = self.ha.states
        for e, s in st.items():
            if e.startswith("weather."):
                return None if (s.get("attributes") or {}).get("temperature") is None else e
        return None

    def outdoor(self) -> float | None:
        e = self.outdoor_sensor()
        return self.c(((self.ha.states.get(e or "") or {}).get("attributes") or {}).get("temperature"))
