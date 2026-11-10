"""The panel and its small API."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

FRONTEND = Path(__file__).parent / "frontend"


def make_app(pilot) -> web.Application:
    async def index(_req: web.Request) -> web.Response:
        return web.FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})

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
    app.router.add_get("/api/diagnostics", diagnostics)
    return app
