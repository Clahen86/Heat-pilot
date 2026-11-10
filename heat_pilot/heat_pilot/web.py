"""The panel and its small API."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

FRONTEND = Path(__file__).parent / "frontend"


def make_app(pilot) -> web.Application:
    async def index(_req: web.Request) -> web.Response:
        """The page, in Home Assistant's own language (not the browser's)."""
        lang = str(pilot.ha.config.get("language") or "en")[:2]
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
    app.router.add_get("/api/diagnostics", diagnostics)
    return app
