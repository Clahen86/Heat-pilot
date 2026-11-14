"""Answers from the developer: one notification per comment, Close hides until a new comment."""

import asyncio
from types import SimpleNamespace

from heat_pilot import support


class Pilot:
    def __init__(self):
        self.settings = {}
        self.calls = []
        self.ha = SimpleNamespace(config={"language": "da"}, call_service=self._call)

    async def _call(self, *a):
        self.calls.append(a)

    def save(self):
        pass

    def lang(self):
        return "da"


def test_answers(monkeypatch):
    p = Pilot()
    s = support.Support(p)
    ans = {"reports": [{"id": "r1", "state": "open", "msgs": [{"from": "dev", "text": "hi", "t": "2026-11-14T08:00:00Z"}]}], "notes": []}

    async def post(path, body, timeout=30):
        return ans

    monkeypatch.setattr(s, "_post", post)
    asyncio.run(s.fetch_answers())
    asyncio.run(s.fetch_answers())
    assert len(p.calls) == 1
    assert len(s.visible()["reports"]) == 1
    s.hide("r1")
    assert s.visible()["reports"] == []
    ans["reports"][0]["msgs"].append({"from": "dev", "text": "more", "t": "2026-11-15T08:00:00Z"})
    asyncio.run(s.fetch_answers())
    assert len(p.calls) == 2 and len(s.visible()["reports"]) == 1
