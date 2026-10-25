"""Server-rendered HTML listing connector.

For venues whose events page is ordinary HTML with no feed behind it (decision 9: no paid
scraping services; decision 3 extended: venues directly, not aggregators). The page is read
once, each listing is found with CSS selectors declared on the source in sources.yaml, and
every date on the listing becomes one Occurrence. Nothing here runs JavaScript: a page that
draws its events in the browser gets nothing from this connector, and the fix is a
conversation with the venue, not a headless browser.

Source entry::

    - id: zeiterion
      kind: html
      url: https://zeiterion.org/events
      select:
        item: ".events-list_item"                  # one node per listing
        title: ".ticket-block_title_text h2"       # text
        url: "a[href^='/events/']"                 # href, made absolute against the page
        when: ".ticket-block_info_text"            # every node; their text is joined and
                                                   # scanned for dates and times
        venue: ".venue"                            # optional text selectors
        town: ".town"
        cost: ".price"
        description: ".blurb"

Dates are human-readable and site-specific ("Friday Oct 30 8:00 pm", "Sat 3:00 pm Oct 31
Sun 3:00 pm Nov 1"). parse_when() finds every month-and-day and pairs each with the nearest
time; a missing year is the next one that puts the date within the window. A listing with no
date at all ("Monthly at Horseneck Beach") yields nothing and is counted in the source note.

Zero listings on a page that loaded is an error, not an empty result: the usual way these
break is a redesign, and the run report must show the venue failing, not quietly absent.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from bs4.element import Tag
from ..models import Occurrence
from .base import Connector

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(20\d\d))?\b", re.I)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", re.I)
# Past this many days behind `now`, a year-less date is taken to mean next year.
LOOKBACK_DAYS = 45


def parse_when(text: str, now: datetime) -> list[datetime]:
    """Every (date, nearest time) pair in `text`, timezone-aware in now's zone, sorted.
    Dates without a time are returned at midnight and flagged all-day by the caller."""
    text = re.sub(r"\s+", " ", text or "")
    dates = list(_DATE.finditer(text))
    if not dates:
        return []
    times = list(_TIME.finditer(text))
    used: set[int] = set()
    out = []
    for d in dates:
        month, day = MONTHS[d.group(1).lower()[:3]], int(d.group(2))
        year = int(d.group(3)) if d.group(3) else None
        nearest, best = None, None
        for i, t in enumerate(times):
            if i in used:
                continue
            dist = min(abs(t.start() - d.end()), abs(d.start() - t.end()))
            if best is None or dist < best:
                nearest, best = i, dist
        hour = minute = 0
        if nearest is not None:
            used.add(nearest)
            t = times[nearest]
            hour, minute = int(t.group(1)) % 12, int(t.group(2) or 0)
            if t.group(3).lower().startswith("p"):
                hour += 12
        try:
            if year is None:
                year = now.year
                cand = datetime(year, month, day, hour, minute, tzinfo=now.tzinfo)
                if cand < now - timedelta(days=LOOKBACK_DAYS):
                    year += 1
            dt = datetime(year, month, day, hour, minute, tzinfo=now.tzinfo)
        except ValueError:          # Feb 30 and friends
            continue
        out.append((dt, nearest is not None))
    out.sort(key=lambda x: x[0])
    return [dt for dt, _ in out]


def has_time(text: str) -> bool:
    return bool(_TIME.search(text or ""))


class HtmlConnector(Connector):
    def fetch(self) -> list[Occurrence]:
        page = self.fetch_text(self.source["url"])
        occs = self.parse(page)
        if not occs:
            raise ValueError(f"no listings found at {self.source['url']}; the selectors are probably stale")
        return [o for o in occs if o.start <= self.horizon and o.start >= self.now - timedelta(days=1)]

    # -- parsing, separated from fetching so the tests can feed a saved page

    def parse(self, page: str) -> list[Occurrence]:
        sel = self.source.get("select") or {}
        if "item" not in sel or "title" not in sel or "when" not in sel:
            raise ValueError(f"{self.id}: an html source needs select.item, select.title and select.when")
        soup = BeautifulSoup(page, "html.parser")
        base_url = self.source["url"]
        out: list[Occurrence] = []
        seen: set[str] = set()
        for item in soup.select(sel["item"]):
            title = _text(item, sel["title"])
            if not title:
                continue
            url = _href(item, sel.get("url"), base_url)
            when_text = " ".join(n.get_text(" ", strip=True) for n in item.select(sel["when"]))
            starts = parse_when(when_text, self.now)
            if not starts:
                continue
            venue = _text(item, sel.get("venue")) or self.source.get("venue", "")
            town = _text(item, sel.get("town"))
            cost = _text(item, sel.get("cost"))
            desc = _text(item, sel.get("description"))
            timed = has_time(when_text)
            for start in starts:
                uid = f"{url or title}#{start.isoformat()}"
                if uid in seen:
                    continue
                seen.add(uid)
                out.append(Occurrence(
                    source_id=self.id, source_uid=uid, title=title, start=start, end=None,
                    all_day=not timed, venue_raw=venue, town=town, url=url or base_url,
                    description=desc, cost=cost, source_categories=[]))
        return out


def _text(node: Tag, selector: str | None) -> str:
    if not selector:
        return ""
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else ""


def _href(node: Tag, selector: str | None, base: str) -> str:
    if not selector:
        return ""
    found = node.select_one(selector)
    href = found.get("href") if found else None
    return urljoin(base, href) if href else ""
