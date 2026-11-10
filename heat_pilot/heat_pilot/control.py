"""Sending: only in the rooms turned to control, only what must change, at a pace each brand can take.

- A room is "shadow" (worked out and shown, nothing sent - the start for every room), "control" or "off".
- Only what differs is sent: the hvac mode and preset only when they are wrong, the setpoint only when it is off by
  more than half the thermostat's step.
- Cloud thermostats (tado°, Netatmo …) get at most one change every few minutes (their request limits).
- A thermostat that didn't take a change (a lost Zigbee command) gets it again after 5 minutes.
- Every setpoint Heat Pilot writes is remembered, so the thermostat's echo is never taken as someone turning it.
- Summer: once a week, Monday 11:00, each valve opens fully for a few minutes and closes again, so it can't
  stick over the summer.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)
RETRY_MIN = 5
EXERCISE_MIN = 5


class Sender:
    def __init__(self) -> None:
        self.last: dict[str, datetime] = {}  # entity -> when Heat Pilot last wrote it
        self.log: list[dict[str, Any]] = []

    def due(self, calls: list[dict[str, Any]], states: dict[str, Any], gaps: dict[str, float], now: datetime,
            step_of: dict[str, float]) -> list[dict[str, Any]]:
        """The calls that must go now: they change something, and the thermostat isn't written too often."""
        out = []
        for c in calls:
            e = c["data"].get("entity_id")
            s = states.get(e) or {}
            a = s.get("attributes") or {}
            if c["service"] == "set_hvac_mode" and s.get("state") == c["data"]["hvac_mode"]:
                continue
            if c["service"] == "set_preset_mode" and a.get("preset_mode") == c["data"]["preset_mode"]:
                continue
            if c["service"] == "set_temperature":
                cur = a.get("temperature")
                try:
                    if cur is not None and abs(float(cur) - float(c["data"]["temperature"])) < step_of.get(e, 0.5) / 2 + 0.01:
                        continue
                except (TypeError, ValueError):
                    pass
            last = self.last.get(e)
            gap = max(gaps.get(e, 1.0), RETRY_MIN if last else 0)
            if last and now - last < timedelta(minutes=gap):
                continue  # just written: give it time (and cloud brands their pace)
            out.append(c)
        return out

    async def send(self, ha: Any, calls: list[dict[str, Any]], now: datetime, wrote) -> None:
        for c in calls:
            e = c["data"].get("entity_id")
            try:
                await ha.call_service(c["domain"], c["service"], dict(c["data"]))
                self.last[e] = now
                if c["service"] == "set_temperature":
                    wrote(e, c["data"]["temperature"], now)
                self.log.insert(0, {"t": now.isoformat(), "call": f"{c['domain']}.{c['service']}", "data": c["data"], "ok": True})
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not send %s.%s to %s: %s", c["domain"], c["service"], e, err)
                self.log.insert(0, {"t": now.isoformat(), "call": f"{c['domain']}.{c['service']}", "data": c["data"], "ok": False})
        del self.log[60:]


def exercise_now(now: datetime, summer: bool) -> bool:
    """Monday 11:00-11:05 in summer: valves open fully for a moment."""
    return summer and now.weekday() == 0 and now.hour == 11 and now.minute < EXERCISE_MIN
