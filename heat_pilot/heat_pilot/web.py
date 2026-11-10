"""The panel and its small API."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

FRONTEND = Path(__file__).parent / "frontend"


def make_app(pilot) -> web.Application:
    async def index(req: web.Request) -> web.Response:
        """The page, in Home Assistant's own language (not the browser's) - or ?lang=de to see another."""
        q = str(req.query.get("lang", ""))[:2]
        lang = q if q in ("da", "en", "de", "fr", "nl", "sv", "nb") else pilot.lang()
        html = (FRONTEND / "index.html").read_text().replace("__HA_LANG__", lang)
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})

    async def status(_req: web.Request) -> web.Response:
        return web.json_response(pilot.status())

    async def room(req: web.Request) -> web.Response:
        body = await req.json()
        area = str(body.pop("area_id", ""))
        if not area:
            return web.json_response({"ok": False}, status=400)
        pilot.set_room(area, body)
        pilot.tick()
        return web.json_response({"ok": True})

    async def feature(req: web.Request) -> web.Response:
        body = await req.json()
        pilot.set_feature(str(body.get("key")), bool(body.get("on")))
        pilot.tick()
        return web.json_response({"ok": True})

    async def district(req: web.Request) -> web.Response:
        pilot.set_district(await req.json())
        pilot.tick()
        return web.json_response({"ok": True})

    async def vent(req: web.Request) -> web.Response:
        pilot.set_ventilation(await req.json())
        pilot.tick()
        return web.json_response({"ok": True})

    async def messages(req: web.Request) -> web.Response:
        pilot.set_messages(await req.json())
        return web.json_response({"ok": True})

    async def tune(req: web.Request) -> web.Response:
        body = await req.json()
        pilot.set_tune(str(body.get("key")), body.get("value"))
        pilot.tick()
        return web.json_response({"ok": True})

    async def history(req: web.Request) -> web.Response:
        """A room's last 24 hours (the room temperature, every 15 minutes) and its plan for the next 24."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        area = req.query.get("area", "")
        room = next((r for r in pilot.rooms() if r["area_id"] == area), None)
        if not room:
            return web.json_response({"past": [], "plan": []})
        tz = ZoneInfo(pilot.ha.config.get("time_zone") or "UTC")
        end = datetime.now(tz)
        start = end - timedelta(hours=24)
        past: list = []
        e = room.get("temp_sensor") or (room["thermostats"][0]["entity_id"] if room["thermostats"] else None)
        if e:
            try:
                rows = (await pilot.ha.history(e, start, end) or [[]])[0]
            except Exception:  # noqa: BLE001
                rows = []
            pts = []
            for h in rows:
                if e.startswith("sensor."):
                    unit = ((pilot.ha.states.get(e) or {}).get("attributes") or {}).get("unit_of_measurement") or "°C"
                    v = pilot.c(h.get("state"), unit)
                else:
                    v = pilot.c((h.get("attributes") or {}).get("current_temperature"))
                try:
                    pts.append((datetime.fromisoformat(h["last_changed"]).astimezone(tz), float(v)))
                except (TypeError, ValueError, KeyError):
                    continue
            # One value per quarter hour: the last known one.
            t, i, last = start.replace(minute=start.minute // 15 * 15, second=0, microsecond=0), 0, None
            while t <= end:
                while i < len(pts) and pts[i][0] <= t:
                    last = pts[i][1]
                    i += 1
                if last is not None:
                    past.append({"t": t.isoformat(), "temp": round(last, 2)})
                t += timedelta(minutes=15)
        return web.json_response({"past": past, "plan": pilot.timelines.get(area) or []})

    async def setup(req: web.Request) -> web.Response:
        pilot.settings["setup_done"] = bool((await req.json()).get("done", True))
        pilot.save()
        return web.json_response({"ok": True})

    async def mode(req: web.Request) -> web.Response:
        body = await req.json()
        pilot.set_mode(body.get("area_id"), str(body.get("mode")))
        pilot.tick()
        return web.json_response({"ok": True})

    async def rediscover(_req: web.Request) -> web.Response:
        await pilot.discover()
        pilot.tick()
        return web.json_response({"ok": True})

    async def diagnostics(_req: web.Request) -> web.Response:
        st = pilot.ha.states
        ents = {t["entity_id"] for r in pilot.found for t in r["thermostats"]}
        ents |= {e for r in pilot.found for e in [r.get("temp_sensor"), *r.get("windows", []), *r.get("presence", [])] if e}
        return web.json_response({"settings": pilot.settings, "found": pilot.found, "now": pilot.now,
                                  "states": {e: st.get(e) for e in sorted(ents)}},
                                 headers={"Content-Disposition": "attachment; filename=heat_pilot_diagnostics.json"})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/room", room)
    app.router.add_post("/api/discover", rediscover)
    app.router.add_post("/api/feature", feature)
    app.router.add_post("/api/district", district)
    app.router.add_post("/api/ventilation", vent)
    app.router.add_post("/api/messages", messages)
    app.router.add_post("/api/tune", tune)
    app.router.add_get("/api/history", history)
    app.router.add_post("/api/setup", setup)
    app.router.add_post("/api/mode", mode)
    app.router.add_get("/api/diagnostics", diagnostics)
    return app
