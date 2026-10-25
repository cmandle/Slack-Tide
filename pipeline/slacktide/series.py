"""Collapse occurrences into series.

Measured 2026-10-11 on Explore New Bedford: 176 rows in 60 days, 56 distinct titles, repeat
ratio 3.14. Hamlet 24 rows, Karaoke 17, nine titles at 8 or 9. Without this step the calendar
shows the same five things every week.

Grouping key is (source, normalised title, canonical venue). The title key ignores a trailing
town ("Eric Lindell - Fall River"), a trailing date ("... - Friday, Nov. 20") and cadence
parentheticals ("(weekly)"). Near-duplicate titles at the same source and venue that share a
start time are one listing posted twice and are merged; the first live run found eight such
pairs at Viva Fall River. Cadence is inferred from the gaps between starts."""
from __future__ import annotations
from collections import defaultdict, Counter
import hashlib, re
from rapidfuzz import fuzz
from .config import TOWNS
from .models import Occurrence, Series

_TOWN_ALT = "|".join(re.escape(t.lower()) for t in sorted(TOWNS, key=len, reverse=True))
_TOWN_SUFFIX = re.compile(r"\s*[-:|]\s*(" + _TOWN_ALT + r")\s*$")
_CADENCE_PAREN = re.compile(r"\((weekly|bi-?weekly|monthly|daily|fortnightly|every [^)]*)\)")
_TRAILING_DATE = re.compile(
    r"\s*[-:,]\s*((mon|tues?|wed(nes)?|thu(rs)?|fri|sat(ur)?|sun)day,?\s*)?"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)\w*\.?\s*\d{1,2}(st|nd|rd|th)?,?\s*(20\d\d)?\s*$")
_DATE_WORDS = re.compile(r"\b(20\d\d|\d{1,2}(st|nd|rd|th)|january|february|march|april|may|june|july|august|september|october|november|december)\b")
NEAR_DUPLICATE = 85

def title_key(t: str) -> str:
    t = t.lower()
    t = _CADENCE_PAREN.sub(" ", t)
    t = _TRAILING_DATE.sub("", t)
    t = _TOWN_SUFFIX.sub("", t)
    t = _DATE_WORDS.sub("", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _weekly_on(starts, weekdays) -> bool:
    """True when every weekday in the set recurs at about seven-day gaps. A Tuesday-and-Thursday
    class has a median gap of two days overall but seven days per weekday."""
    for wd in weekdays:
        ds = [s for s in starts if s.weekday() == wd]
        if len(ds) < 2:
            return False
        gaps = sorted((b - a).days for a, b in zip(ds, ds[1:]))
        if not 6 <= gaps[len(gaps) // 2] <= 8:
            return False
    return True

def _cadence(starts):
    if len({s.date() for s in starts}) == 1:
        return "once", None        # one date, possibly two sittings
    gaps = sorted((b - a).days for a, b in zip(starts, starts[1:]))
    med = gaps[len(gaps) // 2]
    weekdays = {s.weekday() for s in starts}
    if weekdays == {5, 6} and med <= 7:
        return "weekends", None
    if len(weekdays) == 1 and _weekly_on(starts, weekdays):
        return "weekly", starts[0].weekday()
    if len(weekdays) <= 3 and _weekly_on(starts, weekdays):
        return "several-a-week", None
    if med <= 1 and weekdays <= {0, 1, 2, 3, 4} and len(weekdays) >= 4:
        return "weekdays", None
    if med <= 1:
        return "daily", None
    if 13 <= med <= 15 and len(weekdays) == 1:
        return "fortnightly", starts[0].weekday()
    if len(weekdays) == 1 and med <= 31:
        return "monthly", starts[0].weekday()
    return "irregular", None

def _merge_near_duplicates(groups: dict[tuple, list[Occurrence]]) -> None:
    """Merge groups at the same source and venue whose title keys are near-identical and
    which share at least one start time. Smaller groups fold into larger ones."""
    by_source_venue: dict[tuple, list[tuple]] = defaultdict(list)
    for key in groups:
        by_source_venue[(key[0], key[2])].append(key)
    for keys in by_source_venue.values():
        if len(keys) < 2:
            continue
        keys.sort(key=lambda k: -len(groups[k]))
        for i, a in enumerate(keys):
            if a not in groups:
                continue
            a_days = {o.start.date() for o in groups[a]}
            for b in keys[i + 1:]:
                if b not in groups or fuzz.token_set_ratio(a[1], b[1]) < NEAR_DUPLICATE:
                    continue
                if a_days & {o.start.date() for o in groups[b]}:
                    groups[a].extend(groups.pop(b))
                    a_days = {o.start.date() for o in groups[a]}

def _dedupe(items: list[Occurrence]) -> list[Occurrence]:
    """One occurrence per start time. An all-day entry on the same day as a timed one is the same
    listing posted twice (the Narrows posts each concert both ways); the timed one wins."""
    timed_days = {o.start.date() for o in items if not o.all_day}
    seen, out = set(), []
    for o in items:
        if (o.all_day and o.start.date() in timed_days) or o.start in seen:
            continue
        seen.add(o.start)
        out.append(o)
    return out

def _display_title(items: list[Occurrence]) -> str:
    """The most common raw title; ties go to the shortest ("Eric Lindell" over "Eric Lindell - Fall River")."""
    counts = Counter(o.title for o in items)
    return min(counts, key=lambda t: (-counts[t], len(t)))

def collapse(occs: list[Occurrence]) -> list[Series]:
    groups: dict[tuple, list[Occurrence]] = defaultdict(list)
    for o in occs:
        if o.dropped:
            continue
        groups[(o.source_id, title_key(o.title), o.venue.lower())].append(o)
    _merge_near_duplicates(groups)
    out: list[Series] = []
    for (src, tk, vk), items in groups.items():
        items.sort(key=lambda o: o.start)
        title = _display_title(items)   # before de-duplication, so both spellings are weighed
        items = _dedupe(items)
        starts = [o.start for o in items]
        cadence, weekday = _cadence(starts)
        first = items[0]
        sid = hashlib.sha1(f"{src}|{tk}|{vk}".encode()).hexdigest()[:12]
        out.append(Series(
            id=sid, title=title, venue=first.venue, town=first.town,
            category=first.category, source_id=src, url=first.url, cost=first.cost,
            first_start=starts[0], last_start=starts[-1], count=len(items),
            cadence=cadence, weekday=weekday,
            occurrences=[{"start": o.start.isoformat(), "end": o.end.isoformat() if o.end else None,
                          "all_day": o.all_day} for o in items],
            summary=(first.description or "")[:300],
        ))
    out.sort(key=lambda s: s.first_start)
    return out
