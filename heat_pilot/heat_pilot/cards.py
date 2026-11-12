"""The dashboard card: put where Home Assistant serves it (/local/varmepilot/), added to the dashboards' resources,
and fed by sensor.varmepilot (only written when something changed, so it doesn't fill the database)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import shutil
from typing import Any

_LOGGER = logging.getLogger(__name__)
SENSOR = "sensor.varmepilot"
CARD = Path(__file__).parent / "frontend" / "varmepilot-card.js"
HA_CONFIG = Path("/homeassistant")


async def install(ha: Any) -> None:
    if not HA_CONFIG.is_dir():
        _LOGGER.info("Home Assistant's folder isn't mapped: add the card resource by hand")
        return
    target = HA_CONFIG / "www" / "varmepilot" / CARD.name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != CARD.read_bytes():
            shutil.copyfile(CARD, target)
    except OSError:
        _LOGGER.warning("Could not copy the card to %s", target, exc_info=True)
        return
    url = f"/local/varmepilot/{CARD.name}?v={hashlib.sha1(CARD.read_bytes()).hexdigest()[:8]}"
    try:
        resources = await ha.command({"type": "lovelace/resources"})
    except Exception:  # noqa: BLE001 - dashboards in YAML mode: added by hand
        _LOGGER.info("Dashboards in YAML mode: add %s as a module resource", url)
        return
    mine = [r for r in resources if "/local/varmepilot/" in str(r.get("url"))]
    if mine and mine[0]["url"] == url:
        return
    if mine:
        await ha.command({"type": "lovelace/resources/update", "resource_id": mine[0]["id"], "res_type": "module", "url": url})
    else:
        await ha.command({"type": "lovelace/resources/create", "res_type": "module", "url": url})
    _LOGGER.info("Card resource %s", url)


class Publisher:
    def __init__(self) -> None:
        self._last = ""

    @staticmethod
    def room(r: dict[str, Any], pilot: Any, conv) -> dict[str, Any]:
        """One room for the cards: now, the target and why, a hold from the card, and the plan for the next 24 hours."""
        want = r.get("want") or {}
        held = (getattr(pilot, "watch", None) and pilot.watch.manual.get(r["area_id"])) or {}
        tl = r.get("timeline") or []
        step = max(1, len(tl) // 24) if len(tl) > 24 else 1
        plan_ = [[q["t"], conv(q.get("temp")), q.get("why")] for q in tl[::step]][:25]
        after = want.get("until") or ""  # a hold: the next change is when it ends
        nxt = next(({"t": q["t"], "temp": conv(q.get("temp")), "why": q.get("why")} for q in tl
                    if q["t"] >= after and (q.get("temp") != want.get("temp") or q.get("why") != want.get("why"))), None)
        return {"area_id": r["area_id"], "name": r["name"], "sensor": r.get("temp_sensor"), "temp": conv(r.get("temp")),
                "want": conv(want.get("temp")), "why": want.get("why"), "until": want.get("until"), "heating": r.get("heating"),
                "comfort": conv((r.get("cfg") or {}).get("comfort")), "mode": r.get("mode", "shadow"),
                "card": bool(held.get("card")) and want.get("why") == "manual", "boost": bool(held.get("boost")) and want.get("why") == "manual",
                "humidity": (r.get("humidity") or [None])[0], "windows": r.get("windows") or [], "next": nxt, "plan": plan_}

    async def publish(self, ha: Any, pilot: Any) -> None:
        st = pilot.status()
        conv = lambda v: None if v is None else pilot.out_unit(v)  # the card shows the home's own unit (°F in the US)
        rooms = [self.room(r, pilot, conv) for r in st["rooms"] if not r.get("excluded")]
        attrs = {"friendly_name": "Varmepilot", "icon": "mdi:radiator", "rooms": rooms, "sentence": pilot.sentence(),
                 "mode": "shadow" if all(r.get("mode", "shadow") == "shadow" for r in st["rooms"]) else "control",
                 "heating": sum(1 for r in rooms if r["heating"]), "alerts": len(st.get("alerts") or [])}
        v = st.get("vent")
        if v:
            # the ventilation card: the step, the level and why, the room that decides, and the heat recovery (whole
            # degrees, so the sensor isn't written for every tenth)
            t = v.get("temps") or {}
            r0 = lambda x: None if x is None else round(conv(x))
            warn = [{"name": a["name"], "air": a["air"], "co2": a.get("co2"), "hum": a.get("hum")}
                    for a in [{"name": r["name"], **(r.get("air") or {})} for r in st["rooms"]] + (st.get("air_rooms") or [])
                    if a.get("air") in ("warn", "bad")]
            attrs["vent"] = {"level": v.get("level"), "why": v.get("why"), "current": v.get("current"), "step": v.get("step"),
                             "steps": v.get("steps"), "lead": v.get("lead"), "efficiency": v.get("efficiency"), "cooling": v.get("cooling"),
                             "outdoor": r0(t.get("outdoor")), "supply": r0(t.get("supply")), "name": v.get("name"),
                             "agree": v.get("agree"), "mode": v.get("mode") or "shadow", "warn": warn[:3],
                             "hold": v.get("why") if str(v.get("why") or "").startswith("card_") else None}
        key = json.dumps([{k: v for k, v in r.items() if k not in ("temp", "plan")} for r in rooms] + [attrs.get("vent")]
                         + [[(r["plan"] or [[None]])[0][0] for r in rooms], attrs["sentence"], attrs["alerts"]], sort_keys=True, default=str)
        if key == self._last and SENSOR in ha.states:
            return
        await ha.set_state(SENSOR, attrs["heating"], attrs)
        self._last = key
