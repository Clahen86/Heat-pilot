"""Help and answers - the add-on's version of the support module in Clahen86's integrations.

- Get help: the user's message, up to 3 pictures and the diagnostics go privately to the developer (the receiver at
  ep-reports.clahen86.workers.dev files them in a private repository). Only when the user presses Send.
- Answers: when the developer comments on it - or on an error the app reported - the comment is fetched with this
  installation's own id, shown on the Help tab, and gives one notification in Home Assistant per new comment. The user
  can write back and close an answer; a closed issue goes away after a week, a seen answer after two weeks, and a new
  comment brings it back.
- Errors in the app (on unless turned off): the kind of error and where in the code - never the message - once a day
  per error.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import hashlib
import logging
import os
import time
import traceback
from typing import Any
import uuid

_LOGGER = logging.getLogger(__name__)
URL = os.environ.get("HP_REPORT_URL", "https://ep-reports.clahen86.workers.dev")
APP = "heat-pilot"
DAY = 24 * 3600
ANSWER_DAYS, FRESH, CLOSED_KEEP, SEEN_KEEP = 60, 7 * DAY, 7 * DAY, 14 * DAY
NEW_MESSAGE = {
    "da": "💬 Ny besked fra udvikleren. Åbn Varmepilot → 🛟 Hjælp for at læse den.",
    "en": "💬 New message from the developer. Open Heat Pilot → 🛟 Help to read it.",
    "de": "💬 Neue Nachricht vom Entwickler. Öffne Heat Pilot → 🛟 Hilfe, um sie zu lesen.",
    "fr": "💬 Nouveau message du développeur. Ouvrez Heat Pilot → 🛟 Aide pour le lire.",
    "nl": "💬 Nieuw bericht van de ontwikkelaar. Open Heat Pilot → 🛟 Hulp om het te lezen.",
    "sv": "💬 Nytt meddelande från utvecklaren. Öppna Heat Pilot → 🛟 Hjälp för att läsa det.",
    "nb": "💬 Ny melding fra utvikleren. Åpne Heat Pilot → 🛟 Hjelp for å lese den.",
}


class Support:
    def __init__(self, pilot: Any) -> None:
        self.pilot = pilot
        self._errors_sent: dict[str, str] = {}
        self.recent_errors: list[str] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        if not self.d.get("install"):
            self.d["install"] = uuid.uuid4().hex
            self.pilot.save()

    @property
    def d(self) -> dict[str, Any]:
        return self.pilot.settings.setdefault("support", {})

    @property
    def share(self) -> bool:
        return self.d.get("share", True) is not False

    def _save(self) -> None:
        self.pilot.save()

    async def _post(self, path: str, data: dict[str, Any], timeout: int = 30) -> dict[str, Any] | None:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{URL}{path}", json=data, headers={"x-ep-client": APP},
                                  timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                    body = await r.json(content_type=None)
                    return body if r.status == 200 else {"error": (body or {}).get("error") or f"http_{r.status}"}
        except Exception as e:  # noqa: BLE001 - never in the way
            return {"error": "unreachable", "detail": str(e)[:120]}

    # ---------- errors in the app ----------
    def error(self, record: logging.LogRecord) -> None:
        if not record.exc_info or not record.exc_info[1]:
            return
        exc = record.exc_info[1]
        frames = [f for f in traceback.extract_tb(record.exc_info[2]) if "heat_pilot" in f.filename]
        where = f"{os.path.basename(frames[-1].filename)}:{frames[-1].lineno} {frames[-1].name}" if frames else "?"
        text = f"{type(exc).__name__} at {where}"
        self.recent_errors = (self.recent_errors + [text])[-10:]
        if not self.share or not self.loop or os.environ.get("PYTEST_CURRENT_TEST"):
            return
        h = hashlib.sha1(text.encode()).hexdigest()[:16]
        today = date.today().isoformat()
        if self._errors_sent.get(h) == today:
            return
        self._errors_sent[h] = today
        self.d["last_error"] = time.time()
        body = {"kind": "error", "install": self.d["install"], "hash": h, "text": text, "version": os.environ.get("BUILD_VERSION", "dev")}
        self.loop.call_soon_threadsafe(lambda: self.loop.create_task(self._post("/t", body)))

    # ---------- get help ----------
    async def send(self, note: str, images: list[dict[str, Any]], diagnostics: dict[str, Any]) -> dict[str, Any]:
        images = [{"name": str(i.get("name") or "picture")[:60], "data": i["data"]} for i in (images or [])[:3]
                  if isinstance(i, dict) and isinstance(i.get("data"), str) and len(i["data"]) <= 2_000_000]
        diag = {"version": os.environ.get("BUILD_VERSION", "dev"),
                "ha": {k: self.pilot.ha.config.get(k) for k in ("version", "country", "language", "time_zone")},
                "errors": self.recent_errors, **diagnostics}
        res = await self._post("/", {"note": str(note or "")[:4000], "images": images, "diagnostics": diag,
                                     "lang": self.pilot.lang(), "install": self.d["install"]}, timeout=60)
        if res and res.get("ok"):
            self.d["last_help"] = {"id": res.get("id"), "t": time.time()}
            self.d["replies"] = {}
            self._save()
            return {"ok": True, "id": res.get("id")}
        return {"ok": False, "error": (res or {}).get("error", "unreachable")}

    # ---------- answers ----------
    def _last_sent(self) -> float:
        return max(float((self.d.get("last_help") or {}).get("t") or 0), float(self.d.get("last_error") or 0))

    def answer_every(self) -> float | None:
        age = time.time() - self._last_sent()
        if age < ANSWER_DAYS * DAY:
            return 590 if age < FRESH else 3000
        return DAY if self.share else None

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        await asyncio.sleep(120)
        while True:
            try:
                every = self.answer_every()
                if every and time.time() - float((self.d.get("replies") or {}).get("t") or 0) >= every:
                    await self.fetch_answers()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Answer round failed", exc_info=True)
            await asyncio.sleep(600)

    async def fetch_answers(self) -> None:
        d = await self._post("/replies", {"install": self.d["install"]})
        if not d or "reports" not in d:
            return
        self.d["replies"] = {"reports": d["reports"][:5], "notes": (d.get("notes") or [])[:5], "t": time.time()}
        newest = max((self._newest(r) for r in self.d["replies"]["reports"] + self.d["replies"]["notes"]), default="")
        seen = self.d.get("seen") if isinstance(self.d.get("seen"), str) else ""
        self.d["seen"] = max(newest, seen)
        self._save()
        if newest > seen:  # once per new comment - closing the issue changes nothing
            try:
                await self.pilot.ha.call_service("persistent_notification", "create", {
                    "notification_id": "heat_pilot_answer", "title": "Heat Pilot",
                    "message": NEW_MESSAGE.get(self.pilot.lang(), NEW_MESSAGE["en"])})
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _key(r: dict[str, Any]) -> str:
        return str(r.get("id") or "e:" + hashlib.sha1(str(r.get("error")).encode()).hexdigest()[:12])

    @staticmethod
    def _newest(r: dict[str, Any]) -> str:
        return max((str(m.get("t") or "") for m in r.get("msgs") or [] if m.get("from") == "dev"), default="")

    def visible(self, mark_seen: bool = False) -> dict[str, Any]:
        got = self.d.get("replies") or {}
        hidden, shown = self.d.get("hidden") or {}, self.d.setdefault("shown", {})
        now, out = time.time(), {"reports": [], "notes": []}
        for kind in ("reports", "notes"):
            for r in got.get(kind) or []:
                k, new = self._key(r), self._newest(r)
                if k in hidden and hidden[k] >= new:
                    continue
                closed = r.get("closed_at")
                try:
                    if closed and datetime.fromisoformat(str(closed).replace("Z", "+00:00")).timestamp() < now - CLOSED_KEEP and new <= closed:
                        continue
                except ValueError:
                    pass
                sh = shown.get(k)
                if new and sh and sh.get("t") == new and now - float(sh.get("at") or 0) > SEEN_KEEP:
                    continue
                if mark_seen and new and (not sh or sh.get("t") != new):
                    shown[k] = {"t": new, "at": now}
                out[kind].append({**r, "key": k})
        return out

    async def status(self) -> dict[str, Any]:
        if self.answer_every() and time.time() - float((self.d.get("replies") or {}).get("t") or 0) > 300:
            await self.fetch_answers()
        out = {"share": self.share, "last_help": self.d.get("last_help"), "answers": self.visible(mark_seen=True)}
        self._save()
        return out

    def hide(self, key: str) -> None:
        got = self.d.get("replies") or {}
        r = next((x for kind in ("reports", "notes") for x in got.get(kind) or [] if self._key(x) == key), None)
        if r is not None:
            self.d.setdefault("hidden", {})[key] = self._newest(r)
            self._save()

    async def reply(self, report_id: str, text: str) -> dict[str, Any]:
        res = await self._post("/reply", {"install": self.d["install"], "id": str(report_id)[:40], "text": str(text)[:4000]})
        if res and res.get("ok"):
            await self.fetch_answers()
            return {"ok": True}
        return {"ok": False, "error": (res or {}).get("error", "unreachable")}


class ErrorHandler(logging.Handler):
    def __init__(self, support: Support) -> None:
        super().__init__(level=logging.WARNING)
        self.s = support

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.s.error(record)
        except Exception:  # noqa: BLE001
            pass
