"""Start: connect to Home Assistant, find the rooms, work out every minute, serve the panel."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from . import cards
from .engine import Pilot
from .ha import HomeAssistant
from .web import make_app


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ha = HomeAssistant()
    pilot = Pilot(ha, Path(os.environ.get("DATA_DIR", "/data")))
    asyncio.create_task(ha.run())

    async def loop() -> None:
        await ha.connected.wait()
        try:
            await cards.install(ha)
        except Exception:  # noqa: BLE001
            logging.getLogger("heat_pilot").warning("Card not installed", exc_info=True)
        pub = cards.Publisher()
        rounds = 0
        while True:
            try:
                if rounds % 60 == 0 or not pilot.found:
                    await pilot.discover()
                    if rounds == 0:
                        await pilot.seed_history()
                if rounds % 30 == 0:
                    await pilot.refresh_forecast()
                pilot.tick()
                await pilot.control()  # only rooms turned to control - every room starts in shadow
                await pilot.publish()
                await pilot.send_alerts()
                await pub.publish(ha, pilot)
            except Exception:  # noqa: BLE001 - tries again next minute
                logging.getLogger("heat_pilot").warning("Round failed", exc_info=True)
            rounds += 1
            await asyncio.sleep(60)

    asyncio.create_task(loop())
    runner = web.AppRunner(make_app(pilot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", "8099"))).start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
