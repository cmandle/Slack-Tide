"""Squarespace events collection connector.

Any Squarespace events page answers ``?format=json`` with the collection and its items:
``upcoming`` and ``past`` lists (``items`` on some templates), each with ``title``,
``startDate`` and ``endDate`` in epoch milliseconds, ``fullUrl``, an ``excerpt`` and ``body``
in HTML, ``tags`` and ``categories``, and a ``location`` block (``addressTitle``,
``addressLine1``, ``addressLine2``) that the site may leave empty, in which case the meeting
place is in the text and the approver reads it there. Found 2026-11-08 on
southcoastgirlswalk.com/our-schedule (SOURCES.md listed it as the forty-line connector to
build); Hatch Street Studios and Sakonnet Vineyard answer the same way.

Source entry::

    - id: south-coast-girls-walk
      kind: squarespace
      url: https://www.southcoastgirlswalk.com/our-schedule     # the collection page, no query
      town: ""                                                   # when the walks move about
"""
from __future__ import annotations
import html
import json
from datetime import datetime, timezone
from urllib.parse import urljoin
import re
from bs4 import BeautifulSoup
from ..models import Occurrence
from .base import Connector
from .html import town_from_text


def body_text(html: str, limit: int = 600) -> str:
    """Readable text from a Squarespace excerpt or body: style and script blocks dropped (the
    body carries per-block CSS), whitespace collapsed, cut at a word boundary."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["style", "script"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return text


class SquarespaceConnector(Connector):
    def fetch(self) -> list[Occurrence]:
        text = self.fetch_text(self.source["url"], params={"format": "json"})
        occs = self.parse(text)
        return [o for o in occs if self.in_window(o.start)]

    def parse(self, text: str) -> list[Occurrence]:
        """Every item in the collection, past ones included; fetch() applies the window."""
        data = json.loads(text)
        if not isinstance(data, dict) or "collection" not in data:
            raise ValueError(f"{self.id}: {self.source['url']}?format=json is not a Squarespace collection")
        items = (data.get("upcoming") or []) + (data.get("items") or []) + (data.get("past") or [])
        base = self.source["url"]
        out: list[Occurrence] = []
        seen: set[str] = set()
        for it in items:
            if not it.get("startDate") or not it.get("title"):
                continue
            uid = str(it.get("id") or it.get("urlId") or it.get("fullUrl") or it["title"])
            if uid in seen:
                continue
            seen.add(uid)
            start = datetime.fromtimestamp(it["startDate"] / 1000, tz=timezone.utc).astimezone(self.tz).replace(microsecond=0)
            end = None
            if it.get("endDate") and it["endDate"] > it["startDate"]:
                end = datetime.fromtimestamp(it["endDate"] / 1000, tz=timezone.utc).astimezone(self.tz).replace(microsecond=0)
            loc = it.get("location") or {}
            venue = html.unescape(loc.get("addressTitle") or "").strip()   # "Carolyn&#39;s Sakonnet Vineyard"
            town_text = " ".join(str(loc.get(k) or "") for k in ("addressLine1", "addressLine2"))
            town = town_from_text(town_text) or ""
            cats = [str(c) for c in (it.get("categories") or []) + (it.get("tags") or []) if c]
            out.append(Occurrence(
                source_id=self.id, source_uid=uid, title=html.unescape(str(it["title"])).strip(), start=start, end=end,
                all_day=bool(it.get("allDay")), venue_raw=venue, town=town or self.town,
                url=urljoin(base, it.get("fullUrl") or ""),
                description=body_text(it.get("excerpt") or "") or body_text(it.get("body") or ""),   # many sites leave the excerpt empty
                cost="", source_categories=cats))
        out.sort(key=lambda o: o.start)
        return out
