"""Standing schedules declared in the registry: the events venues state in prose.

A bar's home page says "Trivia every Wednesday from 7-9PM"; AHA! Night is the second Thursday of
every month. Nothing machine-readable carries these, so the editor declares them on a
``recurring`` source and this connector expands each declaration into dated occurrences across
the collection window. Every declaration records where the schedule was seen and when, so it can
be re-checked; a series that stops is removed from the registry. Publication still passes the
approver (decision 11), and the series id is the usual hash of source, title and venue, so one
decision covers every date.

Source entry::

    - id: standing-new-bedford
      kind: recurring
      town: New Bedford                   # default town for the series below
      series:
        - title: Trivia night
          venue: PLAY Arcade
          weekday: wednesday              # every <weekday> ...
          week: 2                         # ... or only the Nth <weekday> of the month (-1 = last)
          start: "19:00"                  # omit for an all-day entry
          end: "21:00"                    # optional; at or before start means past midnight
          url: https://www.playarcadenb.com/
          category: Sports & Recreation   # optional, one of config.CATEGORIES; the editor's call, kept as is
          cost: Free                      # optional
          description: ""                 # optional
          town: New Bedford               # optional, overrides the source default
          until: 2027-06-30               # optional last date
          skip: [2026-12-24]              # optional dates that do not happen
          enabled: true                   # false keeps the entry on file without expanding it
          confirmed: 2026-11-08           # when the schedule was last seen ...
          confirmed_at: https://...       # ... and where

Dates may be written bare (YAML reads them as dates) or quoted.
"""
from __future__ import annotations
from datetime import date, datetime, time, timedelta
import re
from ..config import CATEGORIES
from ..models import Occurrence
from .base import Connector

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.I)


def parse_weekday(value) -> int:
    """'wednesday', 'Wed' or 2 -> 2. Raises ValueError on anything else."""
    if isinstance(value, int) and 0 <= value <= 6:
        return value
    key = str(value or "").strip().lower()[:3]
    if key not in WEEKDAYS:
        raise ValueError(f"unknown weekday {value!r}")
    return WEEKDAYS[key]


def parse_time(value) -> time | None:
    """'19:00', '7pm', '7:30 PM' or None. Raises ValueError on anything else."""
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    m = _TIME.match(str(value))
    if not m:
        raise ValueError(f"unknown time {value!r}")
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap.startswith("p") and h < 12:
        h += 12
    if ap.startswith("a") and h == 12:
        h = 0
    if not (0 <= h <= 24 and 0 <= mi < 60):
        raise ValueError(f"unknown time {value!r}")
    return time(h % 24, mi)


def parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def nth_weekday_match(d: date, week: int) -> bool:
    """True when `d` is the `week`th occurrence of its weekday in its month; -1 means the last."""
    if week == -1:
        return (d + timedelta(days=7)).month != d.month
    return (d.day - 1) // 7 + 1 == week


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class RecurringConnector(Connector):
    def fetch(self) -> list[Occurrence]:
        out: list[Occurrence] = []
        for entry in self.source.get("series") or []:
            if not entry.get("enabled", True):
                continue
            out.extend(self.expand(entry))
        return out

    def expand(self, entry: dict) -> list[Occurrence]:
        title = str(entry.get("title") or "").strip()
        if not title:
            raise ValueError(f"{self.id}: a series needs a title")
        weekday = parse_weekday(entry.get("weekday"))
        week = entry.get("week")
        if week is not None and (not isinstance(week, int) or week == 0 or week > 5 or week < -1):
            raise ValueError(f"{self.id}: {title}: week must be 1 to 5 or -1, not {week!r}")
        start_t, end_t = parse_time(entry.get("start")), parse_time(entry.get("end"))
        until = parse_date(entry.get("until"))
        skip = {parse_date(d) for d in (entry.get("skip") or [])}
        venue = str(entry.get("venue") or "")
        town = str(entry.get("town") or self.town)
        category = str(entry.get("category") or "")
        if category and category not in CATEGORIES:
            raise ValueError(f"{self.id}: {title}: category {category!r} is not in config.CATEGORIES")
        uid_base = _slug(f"{title} {venue}")

        first = (self.now - timedelta(days=1)).date()
        last = self.horizon.date()
        if until and until < last:
            last = until
        out: list[Occurrence] = []
        d = first
        while d <= last:
            if d.weekday() == weekday and (week is None or nth_weekday_match(d, week)) and d not in skip:
                start = datetime.combine(d, start_t or time(0, 0), tzinfo=self.tz)
                end = None
                if start_t and end_t:
                    end = datetime.combine(d, end_t, tzinfo=self.tz)
                    if end <= start:
                        end += timedelta(days=1)
                out.append(Occurrence(
                    source_id=self.id, source_uid=f"{uid_base}:{d.isoformat()}", title=title,
                    start=start, end=end, all_day=start_t is None, venue_raw=venue, town=town,
                    url=str(entry.get("url") or ""), description=str(entry.get("description") or ""),
                    cost=str(entry.get("cost") or ""), source_categories=[category] if category else [],
                    category=category))   # the editor's call; normalize keeps a category already set
            d += timedelta(days=1)
        return out
