"""WordPress 'The Events Calendar' REST connector.

Endpoint: /wp-json/tribe/events/v1/events?per_page=50&page=N&start_date=YYYY-MM-DD
Observed in the wild (2026-10-11):
  - explorenewbedford.org: 1,020 future events, clean JSON, 21 pages at 50/page.
  - buzzardsbrew.com: 3,445 bytes of PHP warnings BEFORE the JSON body with a JSON content-type.
    parse_json() skips to the first '{' so this does not break the run.
  - Titles and venue names carry HTML entities (&amp; &#038; &#8211;). Decoded in normalize.
"""
from __future__ import annotations
import json
from datetime import datetime
from ..models import Occurrence
from .base import Connector

def parse_json(text: str) -> dict:
    """Tolerate garbage before the JSON object (PHP notices leaking from a theme)."""
    i = text.find("{")
    if i < 0:
        raise ValueError("no JSON object in response")
    return json.loads(text[i:])

class TribeConnector(Connector):
    PER_PAGE = 50
    MAX_PAGES = 40

    def fetch(self) -> list[Occurrence]:
        out: list[Occurrence] = []
        page = 1
        while page <= self.MAX_PAGES:
            params = {"per_page": self.PER_PAGE, "page": page, "start_date": self.now.strftime("%Y-%m-%d")}
            try:
                data = parse_json(self.fetch_text(self.source["url"], params))
            except Exception as e:  # 400 past the last page is normal for this plugin
                if page > 1:
                    break
                raise
            events = data.get("events") or []
            if not events:
                break
            stop = False
            for e in events:
                occ = self._to_occurrence(e)
                if occ is None:
                    continue
                if occ.start > self.horizon:
                    stop = True
                    break
                out.append(occ)
            if stop or page >= int(data.get("total_pages") or 1):
                break
            page += 1
        return out

    def _to_occurrence(self, e: dict) -> Occurrence | None:
        start = self._parse_dt(e.get("start_date"), e.get("utc_start_date"))
        if start is None:
            return None
        end = self._parse_dt(e.get("end_date"), e.get("utc_end_date"))
        venue = e.get("venue") or {}
        if isinstance(venue, list):
            venue = venue[0] if venue else {}
        return Occurrence(
            source_id=self.id,
            source_uid=str(e.get("id") or e.get("global_id") or e.get("url")),
            title=e.get("title") or "",
            start=start, end=end,
            all_day=bool(e.get("all_day")) or start.strftime("%H:%M") == "00:00",
            venue_raw=venue.get("venue") or "",
            town=venue.get("city") or "",
            url=e.get("url") or "",
            description=e.get("description") or "",
            cost=e.get("cost") or "",
            source_categories=[c.get("name", "") for c in (e.get("categories") or [])],
        )

    def _parse_dt(self, local: str | None, utc: str | None) -> datetime | None:
        if not local:
            return None
        try:
            return datetime.strptime(local, "%Y-%m-%d %H:%M:%S").replace(tzinfo=self.tz)
        except ValueError:
            return None
