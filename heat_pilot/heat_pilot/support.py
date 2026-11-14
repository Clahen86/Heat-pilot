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
import re
import time
import traceback
from typing import Any
import uuid

_LOGGER = logging.getLogger(__name__)
URL = os.environ.get("HP_REPORT_URL", "https://ep-reports.clahen86.workers.dev")
APP = "heat-pilot"
DAY = 24 * 3600
ANSWER_DAYS, FRESH, CLOSED_KEEP, SEEN_KEEP = 60, 7 * DAY, 7 * DAY, 14 * DAY
PATCH_WAIT, MINOR_WAIT, IMPORTANT_WAIT, SNOOZE = 7 * DAY, 2 * DAY, 30 * DAY, 7 * DAY
FIXED_MSG = {"da": "✅ Fejlen, du havde i Varmepilot, er rettet i version {v}. Opdater i add-on-butikken.",
             "en": "✅ The error you had in Heat Pilot is fixed in version {v}. Update in the add-on store.",
             "de": "✅ Der Fehler in Heat Pilot ist in Version {v} behoben. Aktualisiere im Add-on-Store.",
             "fr": "✅ L'erreur dans Heat Pilot est corrigée dans la version {v}. Mettez à jour dans la boutique.",
             "nl": "✅ De fout in Heat Pilot is opgelost in versie {v}. Werk bij in de add-on-winkel.",
             "sv": "✅ Felet i Heat Pilot är rättat i version {v}. Uppdatera i tilläggsbutiken.",
             "nb": "✅ Feilen i Heat Pilot er rettet i versjon {v}. Oppdater i tilleggsbutikken."}
IMPORTANT_MSG = {"da": "⬆️ Varmepilot {v} har en vigtig rettelse. Opdater i add-on-butikken.", "en": "⬆️ Heat Pilot {v} has an important fix. Update in the add-on store.",
                 "de": "⬆️ Heat Pilot {v} enthält eine wichtige Korrektur.", "fr": "⬆️ Heat Pilot {v} contient une correction importante.",
                 "nl": "⬆️ Heat Pilot {v} bevat een belangrijke oplossing.", "sv": "⬆️ Heat Pilot {v} har en viktig rättning.", "nb": "⬆️ Heat Pilot {v} har en viktig retting."}
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

    @property
    def full(self) -> bool:
        """"Share my setup": the full entity names too (off unless the user turns it on)."""
        return bool(self.d.get("full")) and self.share

    def setup_info(self) -> dict[str, Any] | None:
        """How it is set up (setup.py) - only when sharing is on."""
        if not self.share:
            return None
        try:
            from . import setup

            info = setup.collect(self.pilot, self.full)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Setup for the developer failed", exc_info=True)
            return {"failed": True}
        info["full"] = self.full
        return info

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
        if _network(exc):
            return
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
        body: dict[str, Any] = {"install": self.d["install"], "version": self.version()}
        if (su := self.setup_info()) is not None:
            body["setup"] = su
        d = await self._post("/replies", body)
        if not d or "reports" not in d:
            return
        self.d["replies"] = {"reports": d["reports"][:5], "notes": (d.get("notes") or [])[:5], "t": time.time()}
        if isinstance(d.get("latest"), dict) and d["latest"].get("version"):
            self.d["latest"] = d["latest"]
        await self._update_notices()
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

    # ---------- updates (the same rules as the integrations' support module) ----------
    @staticmethod
    def version() -> str:
        return os.environ.get("BUILD_VERSION", "dev")

    @staticmethod
    def _ver(v: Any) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:3]) or (0,)

    def _fixed(self) -> list[dict[str, str]]:
        cur, out = self._ver(self.version()), []
        for n in (self.d.get("replies") or {}).get("notes") or []:
            for m in n.get("msgs") or []:
                hit = re.search(r"fixed in v?(\d+\.\d+(?:\.\d+)?)", str(m.get("text") or ""), re.I)
                if hit and self._ver(hit.group(1)) > cur:
                    out.append({"error": str(n.get("error") or "")[:120], "version": hit.group(1), "key": str(n.get("hash") or n.get("error"))[:60]})
                    break
        return out

    def update(self) -> dict[str, Any] | None:
        lt, cur = self.d.get("latest") or {}, self.version()
        lv, fixed = str(lt.get("version") or ""), self._fixed()
        if not lv or cur == "dev" or self._ver(lv) <= self._ver(cur):
            return None
        now, since = time.time(), self.d.setdefault("behind", {})
        if lv not in since:
            try:
                since[lv] = datetime.fromisoformat(str(lt.get("date"))).timestamp() if lt.get("date") else now
            except ValueError:
                since[lv] = now
        big = self._ver(lv)[:2] > self._ver(cur)[:2]
        snooze = self.d.get("snooze") or {}
        snoozed = now < float(snooze.get("until") or 0) and not (big and self._ver(lv)[:2] > self._ver(snooze.get("version"))[:2])
        due = bool(fixed) or (now - float(since[lv]) >= (MINOR_WAIT if big else PATCH_WAIT) and not snoozed)
        return {"version": lv, "current": cur, "note": str(lt.get("note") or ""), "important": bool(lt.get("important")),
                "repo": str(lt.get("repo") or ""), "big": big, "fixed": fixed, "due": due}

    async def _update_notices(self) -> None:
        u = self.update()
        if not u:
            return
        told, lang, msgs = self.d.setdefault("told", {}), self.pilot.lang(), []
        for f in u["fixed"]:
            if told.get("fixed:" + f["key"]) != f["version"]:
                told["fixed:" + f["key"]] = f["version"]
                msgs.append(("heat_pilot_fixed", FIXED_MSG.get(lang, FIXED_MSG["en"]).format(v=f["version"])))
        if u["important"] and time.time() - float((self.d.get("behind") or {}).get(u["version"]) or time.time()) >= IMPORTANT_WAIT and told.get("important") != u["version"]:
            told["important"] = u["version"]
            msgs.append(("heat_pilot_update", IMPORTANT_MSG.get(lang, IMPORTANT_MSG["en"]).format(v=u["version"])))
        for nid, text in msgs:
            try:
                await self.pilot.ha.call_service("persistent_notification", "create", {"notification_id": nid, "title": "Heat Pilot", "message": text})
            except Exception:  # noqa: BLE001
                pass
        self._save()

    def snooze(self) -> None:
        u = self.update()
        self.d["snooze"] = {"until": time.time() + SNOOZE, "version": (u or {}).get("version") or self.version()}
        self._save()

    async def status(self) -> dict[str, Any]:
        if self.answer_every() and time.time() - float((self.d.get("replies") or {}).get("t") or 0) > 300:
            await self.fetch_answers()
        out = {"share": self.share, "full": self.full, "has_setup": True, "last_help": self.d.get("last_help"), "answers": self.visible(mark_seen=True), "update": self.update()}
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


def _network(exc: BaseException) -> bool:
    """Home Assistant restarting or the network gone (502, timeout, no connection) - not a fault in the app."""
    import asyncio

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    try:
        import aiohttp
    except ImportError:
        return False
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status >= 500
    return isinstance(exc, aiohttp.ClientConnectionError)
