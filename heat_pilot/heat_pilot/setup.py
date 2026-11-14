"""How Heat Pilot is set up - sent once a day with the daily question when sharing is on (see support.py), so the
developer can fix the brand profiles: the thermostats, the ventilation, the heat meter, the hot water tank and the
price sensor - each with its integration, maker and model and what each entity is used for. Entity names are sent
with the user's own device name taken out ("climate.<device>"), and only in full when "Share my setup" is on.
Never sent: room or person names, states over time, addresses.
"""

from __future__ import annotations

import re
from typing import Any

ATTR_NUM = ("unit_of_measurement", "device_class", "min", "max", "step", "min_temp", "max_temp", "target_temp_step")
ATTR_LIST = ("options", "hvac_modes", "preset_modes", "fan_modes", "operation_list")


def _slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(text).lower())).strip("_")


def mask(entity_id: str, regs: dict[str, dict], devs: dict[str, dict]) -> str:
    """The name without the user's own names: the device's name becomes <device>; else the integration's own key;
    else nothing."""
    dom, obj = entity_id.split(".", 1)
    reg = regs.get(entity_id) or {}
    dev = devs.get(reg.get("device_id") or "") or {}
    for n in [x for x in (dev.get("name_by_user"), dev.get("name")) if x]:
        s = _slug(n)
        if s and (obj == s or obj.startswith(s + "_")):
            return f"{dom}.<device>{obj[len(s):]}"
    key = reg.get("translation_key") or (reg.get("has_entity_name") and reg.get("original_name"))
    if key:
        return f"{dom}.<device>_{_slug(key)}"
    return f"{dom}.<name>"


def entity(entity_id: str | None, use: str, states: dict[str, Any], regs: dict[str, dict], devs: dict[str, dict],
           full: bool) -> dict[str, Any] | None:
    if not entity_id:
        return None
    reg = regs.get(entity_id) or {}
    st = states.get(entity_id) or {}
    a = st.get("attributes") or {}
    out: dict[str, Any] = {"name": entity_id if full else mask(entity_id, regs, devs), "use": use, "platform": reg.get("platform")}
    for k in ATTR_NUM:
        if isinstance(a.get(k), (str, int, float)) and len(str(a[k])) < 30:
            out[k] = a[k]
    for k in ATTR_LIST:
        if isinstance(a.get(k), list):
            out[k] = [str(x)[:40] for x in a[k][:25]]
    if reg.get("translation_key"):
        out["key"] = reg["translation_key"]
    if st and entity_id.split(".")[0] in ("select", "switch", "binary_sensor", "climate", "water_heater"):
        out["state"] = str(st.get("state"))[:40]
    return out


def _dev(device_id: str | None, devs: dict[str, dict]) -> dict[str, str]:
    d = devs.get(device_id or "") or {}
    return {"manufacturer": str(d.get("manufacturer") or "")[:60], "model": str(d.get("model") or "")[:60]} if d else {}


def bucket(n: int) -> str:
    return "0" if n <= 0 else "1-3" if n <= 3 else "4-6" if n <= 6 else "7-10" if n <= 10 else "11+"


def collect(p: Any, full: bool) -> dict[str, Any]:
    """The setup of the pilot `p` (engine.Pilot)."""
    st = p.ha.states
    regs, devs = getattr(p, "reg_entities", {}) or {}, getattr(p, "reg_devices", {}) or {}
    ent = lambda e, use: entity(e, use, st, regs, devs, full)  # noqa: E731
    failed: dict[str, int] = {}
    for x in getattr(getattr(p, "sender", None), "log", []) or []:
        if not x.get("ok"):
            e = (x.get("data") or {}).get("entity_id")
            if isinstance(e, str):
                failed[f"{e}|{x.get('call')}"] = failed.get(f"{e}|{x.get('call')}", 0) + 1
    lost = set((getattr(getattr(p, "watchdog", None), "lost", {}) or {}).keys())
    devices: list[dict[str, Any]] = []
    rooms = p.rooms() if hasattr(p, "rooms") else (getattr(p, "found", []) or [])
    for r in rooms:
        for th in r.get("thermostats") or []:
            e = th["entity_id"]
            errs = [f"{k.split('|', 1)[1]} failed ×{n}" for k, n in failed.items() if k.startswith(e + "|")]
            devices.append({"kind": "thermostat", "platform": th.get("platform") or (regs.get(e) or {}).get("platform"),
                            "profile": th.get("brand"), "manufacturer": str(th.get("manufacturer") or "")[:60], "model": str(th.get("model") or "")[:60],
                            "ok": False if th.get("platform") in lost or errs else True, "errors": errs[:5],
                            "entities": [x for x in (ent(e, "thermostat"),) if x],
                            "extra": {"heating": r.get("heating"), "mode": p.mode(r["area_id"]) if hasattr(p, "mode") else None}})
    v = getattr(p, "vent", None)
    if v:
        uses = [("level_select", "level"), ("mode_select", "mode"), ("fan", "fan"), ("bypass", "bypass"),
                ("outdoor", "outdoor"), ("supply", "supply"), ("extract", "extract"), ("exhaust", "exhaust")]
        devices.append({"kind": "ventilation", "platform": v.get("platform"), "manufacturer": str(v.get("manufacturer") or "")[:60],
                        "model": str(v.get("model") or "")[:60], "entities": [x for k, u in uses if (x := ent(v.get(k), u))],
                        "extra": {"mode": (p.settings.get("ventilation") or {}).get("mode") or "shadow"}})
    m = getattr(p, "meter", None)
    if m:
        devices.append({"kind": "meter", "platform": (regs.get(m.get("supply") or "") or {}).get("platform"), **_dev(m.get("device"), devs),
                        "entities": [x for k in ("supply", "return", "flow", "volume") if (x := ent(m.get(k), k))]})
    hw = p.settings.get("hotwater") or {}
    if hw.get("entity"):
        reg = regs.get(hw["entity"]) or {}
        devices.append({"kind": "hotwater", "platform": reg.get("platform"), **_dev(reg.get("device_id"), devs),
                        "entities": [x for x in (ent(hw["entity"], "tank"), ent(hw.get("temp"), "tank_temp")) if x],
                        "extra": {"mode": hw.get("mode") or "shadow"}})
    pe = getattr(p, "price_entity", None)
    if pe:
        devices.append({"kind": "price", "platform": (regs.get(pe) or {}).get("platform"), "entities": [x for x in (ent(pe, "price"),) if x]})
    on = getattr(p, "on", {}) or {}
    modes: dict[str, int] = {}
    heating: dict[str, int] = {}
    for r in rooms:
        if hasattr(p, "mode"):
            modes[p.mode(r["area_id"])] = modes.get(p.mode(r["area_id"]), 0) + 1
        heating[str(r.get("heating") or "?")] = heating.get(str(r.get("heating") or "?"), 0) + 1
    a = getattr(p, "agree", {}) or {}
    return {"devices": devices[:30],
            "features": {k: bool(v) for k, v in on.items()},
            "sizes": {"rooms": bucket(len(rooms)), **{f"heating_{k}": bucket(n) for k, n in heating.items()},
                      **{f"mode_{k}": bucket(n) for k, n in modes.items()}},
            "counts": {"rooms_controlled": modes.get("control", 0),
                       **({"agree_pct": round(100 * a["same"] / a["checks"])} if a.get("checks") else {})}}
