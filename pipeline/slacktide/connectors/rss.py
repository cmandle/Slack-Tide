"""RSS connector. Articles are not events: this stores items for a later extraction pass.
For now it emits nothing to the calendar and writes raw items to the cache for inspection."""
from __future__ import annotations
import feedparser
from ..models import Occurrence
from .base import Connector

class RSSConnector(Connector):
    def fetch(self) -> list[Occurrence]:
        text = self.fetch_text(self.source["url"])
        feed = feedparser.parse(text)
        self.items = [{"title": e.get("title"), "link": e.get("link"), "published": e.get("published")}
                      for e in feed.entries]
        return []
