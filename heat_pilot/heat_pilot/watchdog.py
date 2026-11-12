"""The thermostats that don't do what they are told - and putting the radio right.

Heat Pilot knows what it sent to each thermostat. When a thermostat still shows something else 20 minutes later (or
has gone unavailable), the command was lost on the way. One room is a valve with a weak battery or a bad signal -
the "offline" warning covers that. Two or more rooms on the same integration at once is the radio: Zigbee2MQTT,
ZHA or Matter dropping commands (it happened here on 4 November 2026, 03-07 at night).

Then a warning is shown (and sent, if messages are chosen) and - only when turned on - the integration is restarted:
Zigbee2MQTT's app, or ZHA / Matter reloaded (Matter Server's app if a reload didn't help). At most once in 2 hours per
integration. A cloud thermostat (Tado, Netatmo …) only gets the warning: a restart here doesn't fix their servers.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)
LOST_MIN = 20       # a command not followed for this long is lost
MIN_ROOMS = 2       # rooms on the same integration before it's the radio, not one valve
PAUSE_H = 2         # between two restarts of the same integration
RADIOS = {"mqtt": "Zigbee2MQTT", "zha": "ZHA", "matter": "Matter"}


def disobeying(rooms: list[dict[str, Any]], now_rooms: dict[str, dict[str, Any]], states: dict[str, Any],
               sent: dict[str, tuple[float, datetime]], to_c, controlled) -> list[tuple[str, str, str]]:
    """(room name, thermostat, platform) for the thermostats that don't show what Heat Pilot sent them."""
    out = []
    for r in rooms:
        if not controlled(r["area_id"]):
            continue
        calls = (now_rooms.get(r["area_id"]) or {}).get("calls") or []
        wanted = {c["data"]["entity_id"]: c["data"]["temperature"] for c in calls if c.get("service") == "set_temperature"}
        for th in r.get("thermostats") or []:
            e = th["entity_id"]
            s = states.get(e) or {}
            if s.get("state") in ("unavailable", "unknown"):
                if e in sent:
                    out.append((r["name"], e, th.get("platform") or ""))
                continue
            if e not in wanted or e not in sent:
                continue
            want_c, cur_c = to_c(wanted[e]), to_c((s.get("attributes") or {}).get("temperature"))
            if want_c is None or cur_c is None or abs(want_c - cur_c) <= 0.3:
                continue
            if abs(sent[e][0] - want_c) < 0.05:  # sent, and still not there
                out.append((r["name"], e, th.get("platform") or ""))
    return out


class Watchdog:
    def __init__(self, state: dict[str, Any]) -> None:
        self.s = state.setdefault("watchdog", {"restarted": {}})
        self.since: dict[str, datetime] = {}
        self.lost: dict[str, list[str]] = {}  # platform -> rooms whose commands are lost (for the warning)
        self.just_restarted: dict[str, datetime] = {}

    def see(self, bad: list[tuple[str, str, str]], now: datetime) -> dict[str, list[str]]:
        """platform -> rooms, for the integrations where at least two rooms have lost commands for 20 minutes."""
        bad_e = {e for _, e, _ in bad}
        for e in list(self.since):
            if e not in bad_e:
                self.since.pop(e)
        rooms: dict[str, set[str]] = {}
        for name, e, plat in bad:
            start = self.since.setdefault(e, now)
            if now - start >= timedelta(minutes=LOST_MIN):
                rooms.setdefault(plat, set()).add(name)
        self.lost = {p: sorted(n) for p, n in rooms.items() if len(n) >= MIN_ROOMS}
        return self.lost

    def due(self, platform: str, now: datetime) -> bool:
        last = self.s["restarted"].get(platform)
        return platform in RADIOS and (not last or now - datetime.fromisoformat(last) >= timedelta(hours=PAUSE_H))

    async def restart(self, ha: Any, platform: str, now: datetime) -> str | None:
        """Restart the radio. Returns what was done (None: nothing could be done here)."""
        self.s["restarted"][platform] = now.isoformat()
        try:
            if platform == "mqtt":
                slug = await _addon(ha, "zigbee2mqtt")
                if not slug:
                    return None  # runs outside Home Assistant (Docker): only the warning
                await ha.call_service("hassio", "addon_restart", {"addon": slug})
                return "Zigbee2MQTT"
            if platform in ("zha", "matter"):
                entries = await ha.command({"type": "config_entries/get", "domain": platform})
                for en in entries or []:
                    await ha.call_service("homeassistant", "reload_config_entry", {"entry_id": en["entry_id"]})
                if platform == "matter" and (slug := await _addon(ha, "matter_server")):
                    last = self.just_restarted.get("matter")
                    if last and now - last < timedelta(hours=PAUSE_H * 2):
                        await ha.call_service("hassio", "addon_restart", {"addon": slug})  # the reload alone didn't help last time
                self.just_restarted[platform] = now
                return RADIOS[platform]
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not restart %s", platform, exc_info=True)
        return None


async def _addon(ha: Any, name: str) -> str | None:
    """The slug of an installed app (add-on) whose slug ends in `name`: apps are devices ("hassio", slug) in Home
    Assistant's device registry - None outside Home Assistant OS (Docker) or when it isn't installed."""
    try:
        devices = await ha.command({"type": "config/device_registry/list"})
    except Exception:  # noqa: BLE001
        return None
    for d in devices or []:
        for ident in d.get("identifiers") or []:
            if len(ident) == 2 and ident[0] == "hassio" and str(ident[1]).endswith(name):
                return str(ident[1])
    return None
