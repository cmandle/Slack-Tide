"""Connector base: HTTP with a polite identity, caching, and a window."""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib, json, time
import requests
from ..config import TZ, WINDOW_DAYS
from ..models import Occurrence

USER_AGENT = "SlackTideBot/0.1 (+https://slack-tide.org; community events aggregator; contact hello@slack-tide.org)"
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"

class Connector:
    def __init__(self, source: dict, session: requests.Session | None = None, cache: bool = True):
        self.source = source
        self.id = source["id"]
        self.town = source.get("town", "")
        self.tz = ZoneInfo(TZ)
        self.now = datetime.now(self.tz)
        self.horizon = self.now + timedelta(days=WINDOW_DAYS)
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cache = cache

    def fetch_text(self, url: str, params: dict | None = None, timeout: int = 30) -> str:
        """GET with a one-run cache so re-runs during development do not hammer small sites."""
        key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
        cached = CACHE_DIR / f"{key}.txt"
        if self.cache and cached.exists() and time.time() - cached.stat().st_mtime < 3600:
            return cached.read_text(encoding="utf-8")
        r = self.session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        text = r.text
        if self.cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_text(text, encoding="utf-8")
        return text

    def in_window(self, dt: datetime) -> bool:
        return self.now - timedelta(days=1) <= dt <= self.horizon

    def fetch(self) -> list[Occurrence]:
        raise NotImplementedError
