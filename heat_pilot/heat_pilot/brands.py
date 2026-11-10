"""How each kind of thermostat must be driven - from the integrations' own source and the devices' documentation.

Every thermostat in Home Assistant is a climate entity, so the basics are the same for all: a target temperature,
an hvac mode and maybe presets. What differs - and what makes a heating app work or fail from the start:

- Its own schedule. Tado, Netatmo, Homematic IP, FRITZ!DECT, ecobee, evohome, Danfoss Ally and many Tuya valves
  run a schedule of their own and overwrite our setpoint at their next switch point. They are put in their manual
  mode once, and the setpoint is checked again (re-sent when it has drifted).
- A manual setpoint that runs out. Netatmo's lasts 2 hours (set_temperature in the integration), Tado's ends by
  the zone's own setting (next time block / manual / timer), ecobee's hold by its preference. Re-sent in time.
- No "off". Danfoss Ally and Bosch BTH-RA only have "heat": off is the lowest setpoint instead.
- "Heat" that doesn't regulate. Tuya TS0601 valves in system_mode "heat" stay fully open (Zigbee2MQTT's own
  note) - they regulate in "auto" with the manual preset.
- "Away" that means frost. Aqara E1 (and others) use the away preset as frost protection - away is done with the
  temperature, the preset stays "manual".
- Cloud limits. Tado (a daily request budget) and Netatmo/Nest throttle writes: only real changes are sent, and
  never more often than every few minutes.
- Echoes. Zigbee thermostats report our own write back 15-120 s later; that is never taken as a person turning it.
- The valve's own sensor sits next to the hot radiator. With a room sensor beside it, some valves take the room
  temperature directly (Sonoff TRVZB, Aqara E1, Danfoss Ally, Bosch BTH-RA); for the others the setpoint is offset
  by the difference between the valve and the room.
"""

from __future__ import annotations

import re
from typing import Any

# The feature bits of a climate entity (homeassistant.components.climate.ClimateEntityFeature).
TARGET_TEMPERATURE = 1
PRESET_MODE = 16
TURN_OFF = 128

# By integration (the entity's platform) - what the integration does with a setpoint.
PLATFORMS: dict[str, dict[str, Any]] = {
    "tado": {"name": "tado°", "own_schedule": True, "manual_hvac": "heat", "cloud": True, "min_gap_min": 10,
             "note": "A setpoint is an overlay that ends by the zone's own setting; few requests a day."},
    "netatmo": {"name": "Netatmo", "own_schedule": True, "manual_preset": "manual", "cloud": True, "min_gap_min": 10,
                "expires_min": 120, "note": "A manual setpoint lasts 2 hours - sent again before it ends."},
    "homematicip_cloud": {"name": "Homematic IP", "own_schedule": True, "manual_hvac": "heat", "cloud": True, "min_gap_min": 5,
                          "note": "Heat = manual control mode; auto follows the device's own profile."},
    "fritzbox": {"name": "FRITZ!DECT", "own_schedule": True, "cloud": False, "min_gap_min": 5,
                 "note": "The setpoint holds until the next switch point of the box's own schedule."},
    "ecobee": {"name": "ecobee", "own_schedule": True, "cloud": True, "min_gap_min": 10,
               "note": "A setpoint is a hold, ended by the hold preference."},
    "evohome": {"name": "evohome", "own_schedule": True, "cloud": True, "min_gap_min": 10,
                "note": "A setpoint is a zone override."},
    "nest": {"name": "Google Nest", "cloud": True, "min_gap_min": 5, "no_preset": ["eco"],
             "note": "No setpoint while in eco."},
    "honeywell": {"name": "Honeywell", "own_schedule": True, "cloud": True, "min_gap_min": 10},
    "vicare": {"name": "Viessmann", "cloud": True, "min_gap_min": 15, "whole_house": True,
               "note": "Sets the heating circuit's program temperature - the whole house, not one room."},
    "melcloud": {"name": "MELCloud", "cloud": True, "min_gap_min": 5},
    "daikin": {"name": "Daikin", "cloud": False, "min_gap_min": 2},
    "tuya": {"name": "Tuya", "cloud": True, "min_gap_min": 2},
    "shelly": {"name": "Shelly", "cloud": False, "min_gap_min": 1},
    "mill": {"name": "Mill", "cloud": True, "min_gap_min": 5},
    "generic_thermostat": {"name": "Generic thermostat", "cloud": False, "min_gap_min": 1},
    "better_thermostat": {"name": "Better Thermostat", "cloud": False, "min_gap_min": 1,
                          "note": "Already merges a room sensor and the valves - driven as one thermostat."},
    "versatile_thermostat": {"name": "Versatile Thermostat", "cloud": False, "min_gap_min": 1},
}

# Climate groups (a helper that drives several thermostats as one): the thermostats in them are driven
# directly, never also through the group.
GROUP_PLATFORMS = {"group", "climate_group", "climate_group_helper"}

# By device model (Zigbee2MQTT, ZHA): what the valve itself does.
MODELS: list[tuple[str, dict[str, Any]]] = [
    (r"SRTS-A01|lumi\.airrtc\.agl001|radiator thermostat E1|Aqara.*E1", {"name": "Aqara E1", "manual_preset": "manual", "away_is_frost": True,
                                                  "room_sensor": ("external_temperature_input", "sensor", "external")}),
    (r"W600|lumi\.airrtc\.aeu005", {"name": "Aqara W600", "manual_hvac": "heat", "own_schedule": True}),
    (r"TRVZB", {"name": "SONOFF TRVZB", "manual_hvac": "heat",
                "room_sensor": ("external_temperature_input", "temperature_sensor_select", "external")}),
    (r"014G246[13]|eTRV0100|Ally", {"name": "Danfoss Ally", "no_off": True, "own_schedule": True,
                                    "manual_select": ("programming_operation_mode", "setpoint"),
                                    "room_sensor": ("external_measured_room_sensor", None, None), "room_sensor_scale": 100,
                                    "room_sensor_every_min": 25}),
    (r"BTH-RA", {"name": "Bosch BTH-RA", "no_off": True, "own_schedule": True,
                 "manual_select": ("operating_mode", "manual"), "room_sensor": ("remote_temperature", None, None),
                 "room_sensor_every_min": 25}),
    (r"SPZB0001|Spirit", {"name": "Eurotronic Spirit", "manual_hvac": "heat"}),
    (r"TS0601|TV02|ME167|BRT-100|_TZE2", {"name": "Tuya valve", "manual_preset": "manual", "heat_not_regulating": True,
                                          "own_schedule": True}),
    (r"701721|Popp", {"name": "POPP", "manual_hvac": "heat"}),
]


def profile(platform: str | None, model: str | None, manufacturer: str | None = None) -> dict[str, Any]:
    """What is known about this thermostat: the integration's rules, then the device's own on top."""
    out: dict[str, Any] = {"name": None, "own_schedule": False, "cloud": False, "min_gap_min": 1}
    plat = PLATFORMS.get(platform or "")
    if plat:
        out.update(plat)
    text = " ".join(x for x in (model, manufacturer) if x)
    for pat, p in MODELS:
        if text and re.search(pat, text, re.I):
            out.update(p)
            break
    if not out.get("name"):
        out["name"] = " ".join(x for x in (manufacturer, model) if x) or platform or "Thermostat"
    return out


def can_turn_off(attrs: dict[str, Any], prof: dict[str, Any]) -> bool:
    return "off" in (attrs.get("hvac_modes") or []) and not prof.get("no_off")


def off_calls(entity: str, attrs: dict[str, Any], prof: dict[str, Any]) -> list[dict[str, Any]]:
    """Stop heating: off where the thermostat has it - else its lowest setpoint."""
    if can_turn_off(attrs, prof):
        return [{"domain": "climate", "service": "set_hvac_mode", "data": {"entity_id": entity, "hvac_mode": "off"}}]
    low = float(attrs.get("min_temp") or 5)
    return [{"domain": "climate", "service": "set_temperature", "data": {"entity_id": entity, "temperature": low}}]


def heat_calls(entity: str, attrs: dict[str, Any], prof: dict[str, Any], target: float) -> list[dict[str, Any]]:
    """Heat to a target, in the thermostat's manual mode (never its own schedule, never Tuya's unregulated heat)."""
    calls = []
    modes = attrs.get("hvac_modes") or []
    presets = attrs.get("preset_modes") or []
    hvac = prof.get("manual_hvac") or ("heat" if "heat" in modes else None)
    if prof.get("heat_not_regulating") and "auto" in modes:
        hvac = "auto"  # Tuya TS0601: "heat" stays fully open - "auto" with the manual preset regulates
    if hvac and attrs.get("_state") != hvac and hvac in modes:
        calls.append({"domain": "climate", "service": "set_hvac_mode", "data": {"entity_id": entity, "hvac_mode": hvac}})
    want = prof.get("manual_preset")
    if want and want in presets and attrs.get("preset_mode") != want:
        calls.append({"domain": "climate", "service": "set_preset_mode", "data": {"entity_id": entity, "preset_mode": want}})
    calls.append({"domain": "climate", "service": "set_temperature",
                  "data": {"entity_id": entity, "temperature": round_step(target, attrs)}})
    return calls


def round_step(t: float, attrs: dict[str, Any]) -> float:
    """To the thermostat's own step and range."""
    step = float(attrs.get("target_temp_step") or 0.5)
    lo, hi = float(attrs.get("min_temp") or 5), float(attrs.get("max_temp") or 30)
    return max(lo, min(hi, round(round(t / step) * step, 2)))
