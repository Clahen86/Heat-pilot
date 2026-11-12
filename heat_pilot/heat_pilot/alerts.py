"""Keeping an eye on the house - shown in the app, and sent as a message only if you choose.

Each kind can be turned off on its own, and messages go only to the phones chosen (none until chosen). The same
warning is sent at most once every 12 hours, and not at night unless allowed.

- mold: humidity at 70 % or more for 6 hours - or a cold room (under 16°) at 65 % or more
- air: CO2 over 1,200 ppm for half an hour
- window: a window open for 30 minutes while it is under 10° outside
- offline: a thermostat that has been unavailable for 30 minutes
- battery: a thermostat's or room sensor's battery under 15 % - for a valve that tells its voltage, by the voltage:
  rechargeable AA cells (1.2 V) make it report a low % while they are full
- too_warm: a room more than 2 degrees above its target for 6 hours while it is under 15° outside - the valve
  doesn't close (stuck, or its battery), or something else heats it
- not_warming: a room that has been heating for 3 hours and is still more than a degree below its target -
  air in the radiator, a valve stuck, or a radiator too small
- cooling: district heating cooling well below what is required today
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

KINDS = ["mold", "air", "window", "offline", "battery", "not_warming", "too_warm", "cooling", "monthly"]
REPEAT_H = 12
TOO_WARM = 2.0  # degrees over the target ...
TOO_WARM_H = 6  # ... for this long (the sun alone doesn't keep a room 2 degrees too warm for 6 hours)
CELL_LOW_V = 1.1  # per AA cell: empty below this, alkaline or rechargeable


def cells_ok(states: dict[str, Any], battery: str) -> bool:
    """A battery % that says low while the voltage beside it says fine: rechargeable cells (1.2 V) look nearly empty to
    a valve that expects 1.5 V. Valves run on two AA cells; the voltage sensor sits next to the % (…_voltage)."""
    if not battery.endswith("_battery"):
        return False
    vs = states.get(battery[: -len("_battery")] + "_voltage") or {}
    try:
        v = float(vs.get("state"))
    except (TypeError, ValueError):
        return False
    unit = str((vs.get("attributes") or {}).get("unit_of_measurement") or "mV")
    volts = v / 1000 if unit.lower() == "mv" or v > 100 else v
    return 1.5 < volts < 4.0 and volts / 2 >= CELL_LOW_V


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
                if v is not None and v < 15 and not cells_ok(states, b):
                    out.append({"kind": "battery", "room": name, "key": f"battery:{b}", "level": round(v),
                                "device": (states.get(b) or {}).get("attributes", {}).get("friendly_name") or b})
            want = (n.get("want") or {}).get("temp")
            heating = bool(n.get("heating"))
            below = temp is not None and want is not None and temp < want - 1
            if self._hold(f"warm:{a}", heating and below, now, 180):
                out.append({"kind": "not_warming", "room": name, "key": f"warm:{a}", "temp": temp, "want": want})
            above = temp is not None and want is not None and temp > want + TOO_WARM and outdoor is not None and outdoor < 15
            if self._hold(f"hot:{a}", above and bool(r.get("thermostats")), now, TOO_WARM_H * 60):
                out.append({"kind": "too_warm", "room": name, "key": f"hot:{a}", "temp": round(temp, 1), "want": want})
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
           "too_warm": "{room} er for varmt ({temp}° mod {want}°) i flere timer. Måske sidder ventilen fast åben, eller noget andet varmer rummet.",
           "cooling": "Fjernvarmen: afkøling {today}° i dag – kravet er {need}°. Tjek om nogle radiatorer står helt åbne.",
           "monthly": "Varmepilot i {month}: ca. {pct} % mindre varme end uden. Rummene var varme til tiden {ontime} % af gangene.",
           "title": "Varmepilot"},
    "en": {"mold": "Mould risk in {room}: {hum} % humidity. Air it out and keep the room warmer.",
           "air": "Stale air in {room} ({co2} ppm CO₂). Open a window for a few minutes.",
           "window": "The window in {room} has been open for {minutes} min. Heating is off meanwhile.",
           "offline": "{device} in {room} isn't responding. Check its battery or connection.",
           "battery": "{device} has {level} % left – change the battery.",
           "not_warming": "{room} isn't getting warm ({temp}° of {want}°). Maybe air in the radiator or a stuck valve.",
           "too_warm": "{room} has been too warm for hours ({temp}° vs {want}°). Maybe the valve is stuck open, or something else heats the room.",
           "cooling": "District heating: cooling {today}° today – required is {need}°. Check for radiators fully open.",
           "monthly": "Heat Pilot in {month}: about {pct} % less heat than without. Rooms were warm on time {ontime} % of the time.",
           "title": "Heat Pilot"},
}

TEXT["de"] = {"mold": "Schimmelgefahr in {room}: {hum} % Feuchte. Lüften und den Raum wärmer halten.",
              "air": "Schlechte Luft in {room} ({co2} ppm CO₂). Ein paar Minuten lüften.",
              "window": "Das Fenster in {room} ist seit {minutes} min offen. Die Heizung ist so lange aus.",
              "offline": "{device} in {room} antwortet nicht. Batterie oder Verbindung prüfen.",
              "battery": "{device} hat noch {level} % – Batterie wechseln.",
              "not_warming": "{room} wird nicht warm ({temp}° von {want}°). Vielleicht Luft im Heizkörper oder ein klemmendes Ventil.",
              "too_warm": "{room} ist seit Stunden zu warm ({temp}° statt {want}°). Vielleicht klemmt das Ventil offen, oder etwas anderes heizt den Raum.",
              "cooling": "Fernwärme: Auskühlung heute {today}° – gefordert sind {need}°. Prüfen, ob Heizkörper voll offen stehen.",
              "monthly": "Heat Pilot im {month}: etwa {pct} % weniger Wärme als ohne. Rechtzeitig warm in {ontime} % der Fälle.",
              "title": "Heat Pilot"}
TEXT["fr"] = {"mold": "Risque de moisissure dans {room} : {hum} % d'humidité. Aérez et gardez la pièce plus chaude.",
              "air": "Air vicié dans {room} ({co2} ppm de CO₂). Aérez quelques minutes.",
              "window": "La fenêtre de {room} est ouverte depuis {minutes} min. Le chauffage est coupé en attendant.",
              "offline": "{device} dans {room} ne répond pas. Vérifiez la pile ou la connexion.",
              "battery": "{device} n'a plus que {level} % – changez la pile.",
              "not_warming": "{room} ne chauffe pas ({temp}° sur {want}°). Peut-être de l'air dans le radiateur ou une vanne bloquée.",
              "too_warm": "{room} est trop chaud depuis des heures ({temp}° au lieu de {want}°). La vanne est peut-être bloquée ouverte, ou autre chose chauffe la pièce.",
              "cooling": "Chauffage urbain : refroidissement {today}° aujourd'hui – exigé {need}°. Vérifiez les radiateurs ouverts à fond.",
              "monthly": "Heat Pilot en {month} : environ {pct} % de chaleur en moins. Chaud à temps dans {ontime} % des cas.",
              "title": "Heat Pilot"}
TEXT["nl"] = {"mold": "Schimmelrisico in {room}: {hum} % vocht. Lucht en houd de kamer warmer.",
              "air": "Slechte lucht in {room} ({co2} ppm CO₂). Lucht een paar minuten.",
              "window": "Het raam in {room} staat al {minutes} min open. De verwarming is zolang uit.",
              "offline": "{device} in {room} reageert niet. Controleer batterij of verbinding.",
              "battery": "{device} heeft nog {level} % – vervang de batterij.",
              "not_warming": "{room} wordt niet warm ({temp}° van {want}°). Misschien lucht in de radiator of een vastzittende klep.",
              "too_warm": "{room} is al uren te warm ({temp}° i.p.v. {want}°). Misschien zit de klep open vast, of iets anders verwarmt de kamer.",
              "cooling": "Stadsverwarming: afkoeling vandaag {today}° – vereist is {need}°. Controleer of radiatoren volledig open staan.",
              "monthly": "Heat Pilot in {month}: ongeveer {pct} % minder warmte. Op tijd warm in {ontime} % van de keren.",
              "title": "Heat Pilot"}
TEXT["sv"] = {"mold": "Mögelrisk i {room}: {hum} % fukt. Vädra och håll rummet varmare.",
              "air": "Dålig luft i {room} ({co2} ppm CO₂). Vädra några minuter.",
              "window": "Fönstret i {room} har varit öppet i {minutes} min. Värmen är av så länge.",
              "offline": "{device} i {room} svarar inte. Kontrollera batteri eller anslutning.",
              "battery": "{device} har {level} % kvar – byt batteri.",
              "not_warming": "{room} blir inte varmt ({temp}° av {want}°). Kanske luft i elementet eller en ventil som fastnat.",
              "too_warm": "{room} har varit för varmt i flera timmar ({temp}° mot {want}°). Kanske har ventilen fastnat öppen, eller något annat värmer rummet.",
              "cooling": "Fjärrvärme: avkylning {today}° i dag – kravet är {need}°. Kontrollera om element står helt öppna.",
              "monthly": "Heat Pilot i {month}: ungefär {pct} % mindre värme. Varmt i tid {ontime} % av gångerna.",
              "title": "Heat Pilot"}
TEXT["nb"] = {"mold": "Muggfare i {room}: {hum} % fukt. Luft ut og hold rommet varmere.",
              "air": "Dårlig luft i {room} ({co2} ppm CO₂). Luft ut noen minutter.",
              "window": "Vinduet i {room} har vært åpent i {minutes} min. Varmen er av så lenge.",
              "offline": "{device} i {room} svarer ikke. Sjekk batteri eller tilkobling.",
              "battery": "{device} har {level} % igjen – bytt batteri.",
              "not_warming": "{room} blir ikke varmt ({temp}° av {want}°). Kanskje luft i radiatoren eller en ventil som har satt seg fast.",
              "too_warm": "{room} har vært for varmt i flere timer ({temp}° mot {want}°). Kanskje ventilen står fast åpen, eller noe annet varmer rommet.",
              "cooling": "Fjernvarme: avkjøling {today}° i dag – kravet er {need}°. Sjekk om radiatorer står helt åpne.",
              "monthly": "Heat Pilot i {month}: omtrent {pct} % mindre varme. Varmt i tide {ontime} % av gangene.",
              "title": "Heat Pilot"}


def text(a: dict[str, Any], lang: str) -> str:
    t = TEXT.get(lang, TEXT["en"])
    vals = {k: (f"{v:.1f}" if isinstance(v, float) else v) for k, v in a.items()}
    return t[a["kind"]].format(**vals)
