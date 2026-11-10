"""Finding the house: rooms (Home Assistant's areas), their thermostats and their sensors - with nothing set up.

A room is an area with at least one thermostat (climate entity) in it. In each room:
- thermostats: every climate entity, with its brand profile (see brands.py)
- room temperature: a temperature sensor in the room that isn't a thermostat's own, nor outdoor/floor/water/device
- windows and doors: opening sensors in the room
- presence: motion, occupancy and presence sensors in the room
- humidity / CO2: kept for later (who is in the room)
The kind of room (living room, bedroom, bathroom …) and heating (radiator, floor) are guessed from the names,
and can always be changed.
"""

from __future__ import annotations

import re
from typing import Any

from . import brands

NOT_ROOM_TEMP = re.compile(r"outdoor|outside|ude|udendørs|udeluft|exterior|garden|have|floor|gulv|water|vand|"
                           r"radiator|flow|fremløb|retur|return|supply|boiler|tank|device_temperature|cpu|chip|"
                           r"battery|batteri|inverter|growatt|fridge|køle|freezer|fryser|oven|ovn|dew|dug|"
                           r"forecast|prognose|setpoint|target|apparent|feels", re.I)
# A sensor made to steer the heating (Aqara W100 "temperature control", a "thermostat sensor") is the room's.
CONTROL_SENSOR = re.compile(r"termostat|thermostat|styring|control|climate_sensor|regler", re.I)
WINDOW_WORDS = re.compile(r"vindue|window|fenster|fönster|fonster|vindu|fenêtre|fenetre|raam|velux|ovenlys", re.I)
ROOM_KINDS = [
    ("bathroom", r"bad|bath|wc|toilet|douche|dusch|salle de bain"),
    ("bedroom", r"sove|bedroom|schlaf|sovrum|soverom|chambre|slaapkamer"),
    ("kids", r"børn|kids|child|kinder|barn|enfant|værelse"),
    ("kitchen", r"køkken|kitchen|küche|kök|kjøkken|cuisine|keuken"),
    ("living", r"stue|living|wohn|vardagsrum|séjour|salon|woonkamer|dagligstue|alrum"),
    ("office", r"kontor|office|büro|arbeits|bureau|werk"),
]
FLOOR_WORDS = re.compile(r"floor|gulv|fußboden|golv|plancher|vloer|underfloor", re.I)


def _area_of(e: dict[str, Any], devices: dict[str, dict[str, Any]]) -> str | None:
    return e.get("area_id") or (devices.get(e.get("device_id") or "") or {}).get("area_id")


def room_kind(name: str) -> str:
    for kind, pat in ROOM_KINDS:
        if re.search(pat, name, re.I):
            return kind
    return "other"


def find(areas: list[dict[str, Any]], devices_list: list[dict[str, Any]], entities: list[dict[str, Any]],
         states: dict[str, Any]) -> list[dict[str, Any]]:
    devices = {d["id"]: d for d in devices_list}
    area_name = {a["area_id"]: a.get("name") or a["area_id"] for a in areas}
    area_floor = {a["area_id"]: a.get("floor_id") for a in areas}
    by_area: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        if e.get("disabled_by") or e.get("hidden_by") or e["entity_id"] not in states:
            continue
        a = _area_of(e, devices)
        if a:
            by_area.setdefault(a, []).append(e)
    climate_devs = {e.get("device_id") for es in by_area.values() for e in es if e["entity_id"].startswith("climate.") and e.get("device_id")}
    rooms = []
    for area, ents in sorted(by_area.items(), key=lambda kv: area_name.get(kv[0], kv[0]).lower()):
        climates = [e for e in ents if e["entity_id"].startswith("climate.") and e.get("platform") not in brands.GROUP_PLATFORMS]
        if not climates:
            continue
        name = area_name.get(area, area)
        thermostats = []
        for e in climates:
            d = devices.get(e.get("device_id") or "") or {}
            attrs = (states[e["entity_id"]].get("attributes") or {})
            prof = brands.profile(e.get("platform"), d.get("model") or d.get("model_id"), d.get("manufacturer"))
            thermostats.append({
                "entity_id": e["entity_id"], "name": attrs.get("friendly_name") or e["entity_id"], "platform": e.get("platform"),
                "model": d.get("model"), "manufacturer": d.get("manufacturer"), "brand": prof["name"],
                "hvac_modes": attrs.get("hvac_modes") or [], "preset_modes": attrs.get("preset_modes") or [],
                "min_temp": attrs.get("min_temp"), "max_temp": attrs.get("max_temp"), "step": attrs.get("target_temp_step"),
                "floor": bool(FLOOR_WORDS.search(f"{e['entity_id']} {attrs.get('friendly_name', '')} {d.get('model', '')}")),
                "profile": {k: v for k, v in prof.items() if k != "name"},
            })

        def pick(pred) -> list[str]:
            return sorted(e["entity_id"] for e in ents if pred(e, (states[e["entity_id"]].get("attributes") or {})))

        temps = pick(lambda e, a: e["entity_id"].startswith("sensor.") and a.get("device_class") == "temperature"
                     and e.get("device_id") not in climate_devs and not NOT_ROOM_TEMP.search(f"{e['entity_id']} {a.get('friendly_name', '')}"))
        temps.sort(key=lambda x: not CONTROL_SENSOR.search(x + " " + str((states[x].get("attributes") or {}).get("friendly_name", ""))))
        openings = pick(lambda e, a: e["entity_id"].startswith("binary_sensor.") and a.get("device_class") in ("window", "door", "opening", "garage_door"))
        # A contact sensor is often "door" whatever it sits on - the name tells a window ("vindue") from a door.
        is_window = lambda x: (states[x].get("attributes") or {}).get("device_class") in ("window", "opening") or WINDOW_WORDS.search(
            x + " " + str((states[x].get("attributes") or {}).get("friendly_name", "")))
        windows = [x for x in openings if is_window(x)]
        doors = [x for x in openings if not is_window(x)]
        presence = pick(lambda e, a: e["entity_id"].startswith("binary_sensor.") and a.get("device_class") in ("motion", "occupancy", "presence"))
        humidity = pick(lambda e, a: e["entity_id"].startswith("sensor.") and a.get("device_class") == "humidity"
                        and e.get("device_id") not in climate_devs)
        co2 = pick(lambda e, a: e["entity_id"].startswith("sensor.") and a.get("device_class") == "carbon_dioxide")
        lights = pick(lambda e, a: e["entity_id"].startswith("light."))
        # Batteries of the room's own devices (thermostats, sensors) - for the low-battery message.
        own_devs = {e.get("device_id") for e in ents if e.get("device_id") and (e["entity_id"].startswith("climate.") or e["entity_id"] in temps[:1])}
        batteries = sorted(e["entity_id"] for es in by_area.values() for e in es
                           if e.get("device_id") in own_devs and e["entity_id"].startswith("sensor.")
                           and (states[e["entity_id"]].get("attributes") or {}).get("device_class") == "battery")
        floor = all(t["floor"] for t in thermostats) or (room_kind(name) == "bathroom" and any(t["floor"] for t in thermostats))
        rooms.append({"area_id": area, "name": name, "kind": room_kind(name), "floor_id": area_floor.get(area), "heating": "floor" if floor else "radiator",
                      "thermostats": thermostats, "temp_sensor": temps[0] if temps else None, "temp_options": temps,
                      "windows": windows, "doors": doors, "presence": presence, "humidity": humidity[:1], "co2": co2[:1], "lights": lights, "batteries": batteries})
    return rooms


def unplaced(entities: list[dict[str, Any]], devices_list: list[dict[str, Any]], states: dict[str, Any]) -> list[str]:
    """Thermostats with no room - shown so they can be given one."""
    devices = {d["id"]: d for d in devices_list}
    return sorted(e["entity_id"] for e in entities if e["entity_id"].startswith("climate.") and not e.get("disabled_by")
                  and e.get("platform") not in brands.GROUP_PLATFORMS and e["entity_id"] in states and not _area_of(e, devices))


EXIT_WORDS = re.compile(r"entre|entré|hoveddør|hovedør|hoveddor|front|entrance|main_door|haustür|haustur|ytterdør|ytterdörr|"
                        r"voordeur|porte_d_entree|porte_entree|yttredør", re.I)


def exit_doors(entities: list[dict[str, Any]], states: dict[str, Any]) -> list[str]:
    """The house's outer doors (front door, entrance): opened and then no movement = everyone left."""
    out = []
    for e in entities:
        eid = e["entity_id"]
        if not eid.startswith("binary_sensor.") or e.get("disabled_by") or eid not in states:
            continue
        a = states[eid].get("attributes") or {}
        if a.get("device_class") in ("door", "opening") and EXIT_WORDS.search(f"{eid} {str(a.get('friendly_name', '')).lower().replace(' ', '_')}"):
            out.append(eid)
    return sorted(out)


def all_doors(entities: list[dict[str, Any]], states: dict[str, Any]) -> list[str]:
    """Every door sensor in the house (to choose a door that affects a room, e.g. to a conservatory)."""
    return sorted(e["entity_id"] for e in entities if e["entity_id"].startswith("binary_sensor.") and not e.get("disabled_by")
                  and e["entity_id"] in states and (states[e["entity_id"]].get("attributes") or {}).get("device_class") in ("door", "garage_door", "opening")
                  and not WINDOW_WORDS.search(e["entity_id"]))
