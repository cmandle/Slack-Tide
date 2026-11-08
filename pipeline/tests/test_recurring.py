"""The recurring connector: declared standing schedules expanded across the window."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from slacktide.config import WINDOW_DAYS
from slacktide.connectors.recurring import RecurringConnector, nth_weekday_match, parse_time, parse_weekday
from slacktide.series import collapse

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)   # the frozen fixture's "now", a Wednesday

SOURCE = {
    "id": "standing-new-bedford", "kind": "recurring", "town": "New Bedford",
    "series": [
        {"title": "Trivia night", "venue": "PLAY Arcade", "weekday": "wednesday", "start": "19:00", "end": "21:00",
         "url": "https://www.playarcadenb.com/", "category": "Sports & Recreation"},
        {"title": "Karaoke", "venue": "PLAY Arcade", "weekday": "Thu", "start": "8pm", "end": "12am",
         "skip": [date(2099, 1, 8)]},
        {"title": "AHA! Night", "venue": "Downtown New Bedford", "weekday": "thursday", "week": 2,
         "start": "17:00", "end": "21:00", "town": "New Bedford"},
        {"title": "Last-Friday walk", "venue": "", "weekday": "friday", "week": -1, "until": "2099-02-28"},
        {"title": "Not yet confirmed", "venue": "New Beige", "weekday": "wednesday", "enabled": False},
    ],
}


def test_parsers():
    assert parse_weekday("wednesday") == 2 and parse_weekday("Thu") == 3 and parse_weekday(6) == 6
    with pytest.raises(ValueError):
        parse_weekday("someday")
    assert parse_time("19:00").hour == 19 and parse_time("7pm").hour == 19
    assert parse_time("7:30 PM").minute == 30 and parse_time("12am").hour == 0 and parse_time(None) is None
    assert nth_weekday_match(date(2026, 11, 12), 2) and not nth_weekday_match(date(2026, 11, 5), 2)
    assert nth_weekday_match(date(2026, 11, 27), -1) and not nth_weekday_match(date(2026, 11, 20), -1)


def test_expansion_weekly_monthly_skip_until_and_disabled(frozen):
    c = RecurringConnector(SOURCE, cache=False)
    occs = c.fetch()
    by_title = {}
    for o in occs:
        by_title.setdefault(o.title, []).append(o)
    assert "Not yet confirmed" not in by_title

    trivia = by_title["Trivia night"]
    assert all(o.start.weekday() == 2 and o.start.hour == 19 and o.end.hour == 21 for o in trivia)
    assert len(trivia) in (WINDOW_DAYS // 7, WINDOW_DAYS // 7 + 1)
    assert trivia[0].start.date() == NOW.date()            # today counts; yesterday is the window's floor
    assert trivia[0].venue_raw == "PLAY Arcade" and trivia[0].town == "New Bedford"
    assert trivia[0].source_categories == ["Sports & Recreation"] and not trivia[0].all_day
    assert trivia[0].source_uid.startswith("trivia-night-play-arcade:2098-12-31")

    karaoke = by_title["Karaoke"]
    assert all(o.start.weekday() == 3 for o in karaoke)
    assert karaoke[0].end - karaoke[0].start == timedelta(hours=4)   # 8pm to midnight crosses the date
    assert date(2099, 1, 8) not in {o.start.date() for o in karaoke}

    aha = by_title["AHA! Night"]
    assert all(o.start.weekday() == 3 and 8 <= o.start.day <= 14 for o in aha)
    assert len(aha) == 3                                     # January, February, March second Thursdays

    walk = by_title["Last-Friday walk"]
    assert [o.start.date() for o in walk] == [date(2099, 1, 30), date(2099, 2, 27)]
    assert walk[0].all_day and walk[0].end is None


def test_series_collapse_sees_weekly_and_monthly_cadence(frozen):
    occs = RecurringConnector(SOURCE, cache=False).fetch()
    for o in occs:
        o.venue = o.venue_raw or "Downtown"
    series = {s.title: s for s in collapse(occs)}
    assert series["Trivia night"].cadence == "weekly" and series["Trivia night"].weekday == 2
    assert series["AHA! Night"].cadence == "monthly"
    assert series["Trivia night"].source_id == "standing-new-bedford"


def test_bad_declarations_fail_loudly(frozen):
    bad = {"id": "x", "kind": "recurring", "town": "New Bedford",
           "series": [{"title": "Oops", "weekday": "thursday", "week": 0}]}
    with pytest.raises(ValueError):
        RecurringConnector(bad, cache=False).fetch()
    with pytest.raises(ValueError):
        RecurringConnector({"id": "x", "kind": "recurring", "series": [{"weekday": "monday"}]}, cache=False).fetch()
