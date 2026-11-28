"""Varmepilot for your AI: tools an assistant (Google, ChatGPT, Claude, a local one) can look the heating up with.

"Is it cold in Lilly's room?", "when will the living room be warm?", "why is the bathroom heating?" - the AI asks
Varmepilot itself. Turned on once in the AI's settings ("Varmepilot" under the tools it may use). Without an AI nothing
changes. Only reads: no tool turns anything (the services heat_pilot.boost/set_temperature stay for that).
"""

from __future__ import annotations

from difflib import SequenceMatcher
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

try:  # newer Home Assistant
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol

_LOGGER = logging.getLogger(__name__)
API_ID = "heat_pilot"
PROMPT = ("Varmepilot plans and runs the heating room by room (thermostats, floor heating, ventilation). Use its tools for "
          "anything about temperatures in rooms, whether a room is heating, when a room will be warm, why, and the "
          "ventilation. Times are local. Answer short, in the user's language.")
WHY = {"comfort": "comfort time", "eco": "saving (nobody there / night)", "preheat": "warming up ahead of comfort time",
       "safe": "safe mode (its own sensor is gone)", "manual": "set by hand", "away": "everyone away", "window": "window open",
       "card_boost": "boost from the card", "card_set": "set from the card", "unit_mode": "the unit's own mode"}


async def _status(hass: HomeAssistant) -> dict[str, Any] | None:
    from . import DOMAIN

    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        return None
    url = entries[0].data["url"].rstrip("/")
    try:
        async with async_get_clientsession(hass).get(f"{url}/api/status", timeout=aiohttp.ClientTimeout(total=10)) as r:
            r.raise_for_status()
            return await r.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):  # ValueError: a cut-off answer that isn't JSON
        return None


def _local(t: str | None) -> str | None:
    try:
        return dt_util.as_local(dt_util.parse_datetime(str(t))).strftime("%a %H:%M") if t else None
    except (TypeError, ValueError, AttributeError):
        return None


def room_view(r: dict[str, Any]) -> dict[str, Any]:
    want = r.get("want") or {}
    nxt = None
    now = dt_util.now()
    for step in r.get("timeline") or []:
        t = dt_util.parse_datetime(str(step.get("t") or ""))
        if t and t > now and step.get("temp") is not None and step.get("temp") != want.get("temp"):
            nxt = {"at": _local(step["t"]), "target": step["temp"], "why": WHY.get(str(step.get("why")), step.get("why"))}
            break
    return {"room": r.get("name"), "temperature": r.get("temp"), "target_now": want.get("temp"),
            "why": WHY.get(str(want.get("why")), want.get("why")), "heating_now": bool(r.get("heating")),
            "someone_there": bool(r.get("occupied")), "humidity": (r.get("air") or {}).get("humidity") if isinstance(r.get("air"), dict) else None,
            "next_change": nxt, "heating_hours_today": r.get("hours_today"), "excluded": bool(r.get("excluded"))}


def pick(rooms: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """The room asked about - also "Lillys værelse" for "Holly & Lilly", or a small slip."""
    q = name.lower().strip()
    hits = [r for r in rooms if q in str(r.get("name") or "").lower() or str(r.get("name") or "").lower() in q]
    if hits:
        return hits
    words = [w for w in q.replace("'s", "").split() if len(w) > 2]
    scored = sorted(((max((SequenceMatcher(None, w, x).ratio() for w in words for x in str(r.get("name") or "").lower().replace("&", " ").split()), default=0), i)
                     for i, r in enumerate(rooms)), reverse=True)
    return [rooms[scored[0][1]]] if scored and scored[0][0] >= 0.75 else []


class Rooms(llm.Tool):
    name = "heat_pilot_rooms"
    integration = "heat_pilot"
    description = ("The heating room by room: temperature now, the target and why, whether it heats now, the next change "
                   "(when it will be warm), and the ventilation and outdoor temperature. Give a room to get only that one.")
    parameters = vol.Schema({vol.Optional("room", description="A room's name, e.g. 'stue' or 'Lillys værelse' (leave out for all)"): str})

    async def async_call(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict[str, Any]:
        st = await _status(hass)
        if not st:
            return {"error": "Varmepilot isn't answering right now"}
        rooms = [r for r in st.get("rooms") or [] if not r.get("excluded")]
        if (room := (tool_input.tool_args or {}).get("room")):
            hit = pick(rooms, str(room))
            if not hit:
                return {"error": f"No room called {room}", "rooms": [r.get("name") for r in rooms]}
            rooms = hit
        vent = st.get("vent") or {}
        return {"unit": st.get("unit"), "outdoor": st.get("outdoor"), "everyone_away": st.get("away"),
                "rooms": [room_view(r) for r in rooms],
                "ventilation": {k: vent.get(k) for k in ("mode", "level", "why") if isinstance(vent, dict) and k in vent} or None,
                "alerts": [a.get("text") for a in st.get("alerts") or [] if a.get("text")]}


class HeatAPI(llm.API):
    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass=hass, id=API_ID, name="Varmepilot")

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(api=self, api_prompt=PROMPT, llm_context=llm_context, tools=[Rooms()])


def register(hass: HomeAssistant) -> Any:
    try:
        return llm.async_register_api(hass, HeatAPI(hass))
    except Exception:  # noqa: BLE001 - already there, or an older Home Assistant
        _LOGGER.debug("Varmepilot tools not registered", exc_info=True)
        return None
