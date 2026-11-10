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

    async def publish(self, ha: Any, pilot: Any) -> None:
        st = pilot.status()
        rooms = [{"area_id": r["area_id"], "name": r["name"], "sensor": r.get("temp_sensor"), "temp": r.get("temp"),
                  "want": (r.get("want") or {}).get("temp"), "why": (r.get("want") or {}).get("why"), "heating": r.get("heating")}
                 for r in st["rooms"] if not r.get("excluded")]
        attrs = {"friendly_name": "Varmepilot", "icon": "mdi:radiator", "rooms": rooms, "sentence": pilot.sentence(),
                 "mode": "shadow" if all(r.get("mode", "shadow") == "shadow" for r in st["rooms"]) else "control",
                 "heating": sum(1 for r in rooms if r["heating"]), "alerts": len(st.get("alerts") or [])}
        key = json.dumps([{k: v for k, v in r.items() if k != "temp"} for r in rooms] + [attrs["sentence"], attrs["alerts"]], sort_keys=True, default=str)
        if key == self._last and SENSOR in ha.states:
            return
        await ha.set_state(SENSOR, attrs["heating"], attrs)
        self._last = key
