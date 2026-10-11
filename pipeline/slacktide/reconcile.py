"""Coverage check against a 'check' role source (Explore New Bedford).

Reports what the check source has that primary sources missed, grouped as series so the list
reads as a connector to-do list rather than 25 rows of Hamlet, and what primaries have that
the check source lacks within the towns the check source covers. Matching is fuzzy on title
within the same calendar day and the same town; the first live run matched 23 Fall River rows
to New Bedford titles before the town constraint was added."""
from __future__ import annotations
from rapidfuzz import fuzz
from .models import Occurrence
from .series import title_key

def reconcile(primary: list[Occurrence], check: list[Occurrence], threshold: int = 85) -> dict:
    by_day_town: dict[tuple, list[Occurrence]] = {}
    for o in primary:
        if not o.dropped:
            by_day_town.setdefault((o.start.date().isoformat(), o.town), []).append(o)

    matched_rows = 0
    missed: dict[tuple, dict] = {}
    for c in check:
        if c.dropped:
            continue
        ck = title_key(c.title)
        candidates = by_day_town.get((c.start.date().isoformat(), c.town), [])
        if any(fuzz.token_set_ratio(ck, title_key(p.title)) >= threshold for p in candidates):
            matched_rows += 1
            continue
        g = missed.setdefault((ck, c.venue.lower()), {
            "title": c.title, "venue": c.venue, "town": c.town, "first_start": c.start.isoformat(), "rows": 0})
        g["rows"] += 1
    missed_list = sorted(missed.values(), key=lambda g: (-g["rows"], g["title"]))
    total = matched_rows + sum(g["rows"] for g in missed_list)

    check_towns = {c.town for c in check if not c.dropped}
    seen = {(c.start.date().isoformat(), c.town, title_key(c.title)) for c in check if not c.dropped}
    extra = [o for o in primary if not o.dropped and o.town in check_towns
             and (o.start.date().isoformat(), o.town, title_key(o.title)) not in seen]
    return {
        "check_total": total,
        "check_matched": matched_rows,
        "check_missed_rows": total - matched_rows,
        "check_missed_series": len(missed_list),
        "check_missed": missed_list,
        "check_towns": sorted(check_towns),
        "primary_only_count": len(extra),
        "primary_only_series": len({(o.source_id, title_key(o.title), o.venue.lower()) for o in extra}),
        "coverage_ratio": round(matched_rows / max(1, total), 3),
    }
