"""The html listing connector and the published-sheet connector, offline against saved pages."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from conftest import fixture_text
from slacktide.connectors.html import HtmlConnector, parse_when
from slacktide.connectors.sheet import SheetConnector, map_columns
from slacktide.normalize import uncap, normalize

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)

ZEITERION = {
    "id": "zeiterion", "kind": "html", "url": "https://zeiterion.org/events", "town": "New Bedford",
    "venue": "The Zeiterion",
    "select": {
        "item": ".events-list_item",
        "title": ".ticket-block_title_text h2",
        "url": "a[href^='/events/']",
        "when": ".ticket-block_info_date_wrapper:not(.w-condition-invisible) .ticket-block_info_text:not(.w-condition-invisible)",
    },
}

def test_parse_when_single_two_date_and_bare_forms():
    now = datetime(2026, 10, 25, 12, tzinfo=TZ)
    one = parse_when("Friday Oct 30 8:00 pm", now)
    assert one == [datetime(2026, 10, 30, 20, 0, tzinfo=TZ)]
    two = parse_when("Sat 3:00 pm Oct 31 Sun 3:00 pm Nov 1", now)
    assert two == [datetime(2026, 10, 31, 15, 0, tzinfo=TZ), datetime(2026, 11, 1, 15, 0, tzinfo=TZ)]
    assert parse_when("Oct 30, 2026 at 7:30 PM", now)[0].hour == 19
    noon = parse_when("Sunday, January 10 at 12pm", now)
    assert noon[0].hour == 12 and noon[0].year == 2027
    assert parse_when("Monthly at Horseneck Beach", now) == []
    assert parse_when("Jan 9 3:00 pm", now)[0].year == 2027      # year-less January from an October vantage rolls forward
    assert parse_when("Oct 1 8:00 pm", now)[0].year == 2026      # three weeks back stays this year (lookback)

def test_html_connector_reads_zeiterion_listing(frozen):
    c = HtmlConnector(ZEITERION, cache=False)
    occs = c.parse(fixture_text("zeiterion_listing.html"))
    by_url = {}
    for o in occs:
        by_url.setdefault(o.url, []).append(o)
    # ad-schooltime is in the fixture with a date but no title (an internal placeholder on the
    # real page) and is skipped.
    assert set(by_url) == {"https://zeiterion.org/events/mystic-pizza", "https://zeiterion.org/events/nbso-allsouls",
                           "https://zeiterion.org/events/wicked-sing-along"}
    pizza = by_url["https://zeiterion.org/events/mystic-pizza"][0]
    assert pizza.title == "MYSTIC PIZZA: A NEW MUSICAL" and pizza.start.strftime("%b %d %H:%M") == "Oct 30 20:00"
    assert pizza.venue_raw == "The Zeiterion" and pizza.all_day is False and pizza.source_id == "zeiterion"
    souls = sorted(o.start for o in by_url["https://zeiterion.org/events/nbso-allsouls"])
    assert [s.strftime("%b %d %H:%M") for s in souls] == ["Oct 31 15:00", "Nov 01 15:00"]   # two-date show, two occurrences
    assert len(occs) == 4
    # The filter chip at the bottom of the page is a dyn item but not an events-list_item.
    assert not any("some-other" in o.url for o in occs)

def test_html_connector_fails_loudly_on_empty_page(frozen, monkeypatch):
    c = HtmlConnector(ZEITERION, cache=False)
    monkeypatch.setattr(c, "fetch_text", lambda url, params=None, timeout=30: "<html><body><p>Redesigned!</p></body></html>")
    with pytest.raises(ValueError):
        c.fetch()

def test_html_connector_needs_its_selectors():
    with pytest.raises(ValueError):
        HtmlConnector({"id": "x", "kind": "html", "url": "https://example.org", "select": {"item": ".a"}}, cache=False).parse("<p>")

def test_uncap_only_touches_shouting_titles():
    assert uncap("MYSTIC PIZZA: A NEW MUSICAL") == "Mystic Pizza: A New Musical"
    assert uncap("GET THE LED OUT") == "Get the Led Out"
    assert uncap("THE PRICE IS RIGHT LIVE ON STAGE") == "The Price Is Right Live on Stage"
    assert uncap("NBSO") == "NBSO"
    assert uncap("Pete the Cat") == "Pete the Cat"
    assert uncap("BINGO!") == "BINGO!"      # a lone word is left alone: it may be an acronym
    assert uncap("Jazz Jam with DJ ABE") == "Jazz Jam with DJ ABE"   # mixed case is left alone
    assert uncap("JAZZ JAM WITH DJ ABE") == "Jazz Jam with DJ Abe"

def test_default_category_is_ours_and_only_fills_gaps(frozen):
    c = HtmlConnector(ZEITERION, cache=False)
    occs = c.parse(fixture_text("zeiterion_listing.html"))
    normalize(occs, {"zeiterion": "New Bedford"}, {"zeiterion": "The Zeiterion"}, {"zeiterion": "Arts & Theatre"})
    by_title = {o.title: o for o in occs}
    assert by_title["Mystic Pizza: A New Musical"].category == "Arts & Theatre"   # from the rule ("musical")
    assert by_title["All Souls"].category == "Arts & Theatre"                    # from the venue default
    assert all(o.town == "New Bedford" and o.venue == "The Zeiterion" for o in occs)

def test_sheet_columns_and_rows(frozen):
    cols = map_columns(["Timestamp", "Event title", "Date", "Start time", "End time", "Venue", "Town", "Listing type", "Category", "Link", "Cost", "Details", "Your name", "Your email", "Status"])
    assert cols["title"] == 1 and cols["start"] == 3 and cols["end"] == 4 and cols["kind"] == 7 and cols["category"] == 8 and cols["url"] == 9 and cols["status"] == 14
    c = SheetConnector({"id": "submissions", "kind": "sheet", "url": "x", "town": ""}, cache=False)
    occs = c.parse(fixture_text("submissions.csv"))
    titles = [o.title for o in occs]
    assert titles == ["Holiday craft fair", "Yoga on the pier", "Sakonnet shore morning"]   # spam status and the dateless row are skipped
    fair, yoga, cleanup = occs
    assert fair.start.isoformat() == "2099-01-10T10:00:00-05:00" and fair.end.hour == 15 and fair.town == "Westport"
    assert yoga.start.isoformat() == "2099-01-12T08:00:00-05:00" and yoga.end is None and yoga.cost == "$10, cash"
    assert "pat@example.org" not in (fair.description + fair.title + fair.venue_raw)   # organiser details never enter a record
    assert cleanup.source_categories == ["Volunteer opportunities", "Volunteering & Causes"]
    normalize(occs, {"submissions": ""}, {})
    assert fair.town == "Westport" and fair.category == "Markets & Fairs"
    assert yoga.category == "Sports & Recreation"            # the rules win when they match
    assert cleanup.category == "Volunteering & Causes"       # no rule word in the title, so the organiser's own category fills the gap
