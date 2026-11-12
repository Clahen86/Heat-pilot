"""Varmepilot in Home Assistant: the dashboard card's buttons as services (the Heat Pilot app does the thinking).

heat_pilot.boost        - a room warmer for a while (60 min)
heat_pilot.set_temperature - a temperature, or a step up/down from now, for a while
heat_pilot.resume       - back to the plan now
Kept apart from turning a thermostat by hand, so Heat Pilot never learns from them.
"""

from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "heat_pilot"

AREA = vol.Required("area_id")
SCHEMAS = {
    "boost": vol.Schema({AREA: cv.string, vol.Optional("minutes", default=60): vol.All(vol.Coerce(float), vol.Range(min=5, max=720))}),
    "set_temperature": vol.Schema({AREA: cv.string, vol.Exclusive("temperature", "how"): vol.Coerce(float),
                                   vol.Exclusive("step", "how"): vol.Coerce(float),
                                   vol.Optional("minutes", default=60): vol.All(vol.Coerce(float), vol.Range(min=5, max=720))}),
    "resume": vol.Schema({AREA: cv.string}),
}
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    url = entry.data["url"].rstrip("/")
    session = async_get_clientsession(hass)

    async def call(service: ServiceCall) -> None:
        body = dict(service.data)
        if service.service == "boost":
            body["boost"] = True
        elif service.service == "resume":
            body["resume"] = True
        try:
            async with session.post(f"{url}/api/hold", json=body, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 404:
                    raise HomeAssistantError(f"Varmepilot doesn't know the room {body.get('area_id')}")
                r.raise_for_status()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Varmepilot isn't answering: {err}") from err

    for name, schema in SCHEMAS.items():
        hass.services.async_register(DOMAIN, name, call, schema=schema)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    for name in SCHEMAS:
        hass.services.async_remove(DOMAIN, name)
    return True
