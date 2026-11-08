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
        end: ".ends"                               # optional; the first time in its text is the end
        page_when: "h2.title, h3.title"            # optional; the page's own date, for listings whose
                                                   # items carry no date (AHA!'s next-night page)
        when_class: "tag-"                         # optional; a time written into the item's class
                                                   # names, WordPress style: tag-200pm is 2:00pm
        start: "17:00"                             # optional; the start when an item has a date but
                                                   # no time of its own
        group_next: 1                              # optional; the item is this node plus the next N
                                                   # element siblings (a date <p> then an artist <p>)

A title that ends in a time ("Day Drinkers 7pm") loses the time; it is read from `when`.

Dates are human-readable and site-specific ("Friday Oct 30 8:00 pm", "Sat 3:00 pm Oct 31
Sun 3:00 pm Nov 1"). parse_when() finds every month-and-day and pairs each with the nearest
time; a missing year is the next one that puts the date within the window. A listing with no
date at all ("Monthly at Horseneck Beach") yields nothing and is counted in the source note.

Zero listings on a page that loaded is an error, not an empty result: the usual way these
break is a redesign, and the run report must show the venue failing, not quietly absent.
"""
from __future__ import annotations
import re
from collections import Counter
from datetime import datetime, time, timedelta
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


def first_time(text: str) -> time | None:
    """The first clock time in `text` ("Ends: 8:00pm" -> 20:00), or None."""
    m = _TIME.search(text or "")
    if not m:
        return None
    hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
    if m.group(3).lower().startswith("p"):
        hour += 12
    return time(hour, minute)


_CLASS_TIME = re.compile(r"^(\d{1,2})(\d{2})?(am|pm)$", re.I)


def times_from_classes(node: Tag, prefix: str) -> str:
    """Class names such as tag-200pm or tag-1130am, written out as '2:00pm 11:30am'."""
    out = []
    for c in node.get("class", []):
        if not c.startswith(prefix):
            continue
        m = _CLASS_TIME.match(c[len(prefix):])
        if m:
            out.append(f"{int(m.group(1))}:{m.group(2) or '00'}{m.group(3).lower()}")
    return " ".join(out)


_TRAILING_TIME = re.compile(
    r"[\s,@|-]*(?:at\s+|from\s+)?(?:\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?\s*(?:-|–|to)\s*)?"
    r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\s*$", re.I)


def strip_trailing_time(title: str) -> str:
    return _TRAILING_TIME.sub("", title or "").strip()


def group_with_next(node: Tag, n: int) -> Tag:
    """A fresh fragment holding `node` and its next `n` element siblings, so that selectors can
    address a listing written as consecutive paragraphs. The page itself is not changed."""
    parts, sib = [str(node)], node
    for _ in range(n):
        sib = sib.find_next_sibling()
        if sib is None:
            break
        parts.append(str(sib))
    return BeautifulSoup("<div>" + "".join(parts) + "</div>", "html.parser").div


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
        if "item" not in sel or "title" not in sel or ("when" not in sel and "page_when" not in sel):
            raise ValueError(f"{self.id}: an html source needs select.item, select.title and select.when (or select.page_when)")
        soup = BeautifulSoup(page, "html.parser")
        base_url = self.source["url"]
        # The page's own date, for listings whose items carry none: the most frequent date in
        # the selected headings, so a stray date in one heading does not win.
        page_date = None
        if sel.get("page_when"):
            heading_text = " ".join(n.get_text(" ", strip=True) for n in soup.select(sel["page_when"]))
            found = [d.date() for d in parse_when(heading_text, self.now)]
            if found:
                page_date = Counter(found).most_common(1)[0][0]
        default_start = first_time(sel["start"]) if sel.get("start") else None
        group_next = int(sel.get("group_next") or 0)
        out: list[Occurrence] = []
        seen: set[str] = set()
        for item in soup.select(sel["item"]):
            if group_next:
                item = group_with_next(item, group_next)
            title = strip_trailing_time(_text(item, sel["title"]))
            if not title:
                continue
            url = _href(item, sel.get("url"), base_url)
            when_text = " ".join(n.get_text(" ", strip=True) for n in item.select(sel["when"])) if sel.get("when") else ""
            if sel.get("when_class"):
                when_text = (when_text + " " + times_from_classes(item, sel["when_class"])).strip()
            starts = parse_when(when_text, self.now)
            timed = has_time(when_text)
            if not starts and page_date is not None:
                t = first_time(when_text) or default_start
                starts = [datetime.combine(page_date, t or time(0, 0), tzinfo=self.tz)]
                timed = t is not None
            if not starts:
                continue
            end_time = first_time(_text(item, sel.get("end"))) if sel.get("end") else None
            venue = _text(item, sel.get("venue")) or self.source.get("venue", "")
            town = _text(item, sel.get("town"))
            cost = _text(item, sel.get("cost"))
            desc = _text_all(item, sel.get("description"))   # every matching node: Elementor splits a body over widgets
            for start in starts:
                uid = f"{url or title}#{start.isoformat()}"
                if uid in seen:
                    continue
                seen.add(uid)
                end = None
                if end_time is not None and timed:
                    end = datetime.combine(start.date(), end_time, tzinfo=self.tz)
                    if end <= start:
                        end += timedelta(days=1)
                out.append(Occurrence(
                    source_id=self.id, source_uid=uid, title=title, start=start, end=end,
                    all_day=not timed, venue_raw=venue, town=town, url=url or base_url,
                    description=desc, cost=cost, source_categories=[]))
        return out


def _text(node: Tag, selector: str | None) -> str:
    if not selector:
        return ""
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else ""


def _text_all(node: Tag, selector: str | None) -> str:
    if not selector:
        return ""
    parts = [n.get_text(" ", strip=True) for n in node.select(selector)]
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return " ".join(out)


def _href(node: Tag, selector: str | None, base: str) -> str:
    if not selector:
        return ""
    found = node.select_one(selector)
    href = found.get("href") if found else None
    return urljoin(base, href) if href else ""
