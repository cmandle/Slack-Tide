"""The html connector's detail pages, offline against the Buzzards Bay Coalition's Bay Adventures
listing and three of the pages behind its cards."""
from datetime import time
import pytest
from conftest import fixture_text
from slacktide.connectors.html import HtmlConnector, last_time, town_from_text

BBC = {
    "id": "buzzards-bay-coalition", "kind": "html", "url": "https://www.savebuzzardsbay.org/events/bay-adventures/",
    "town": "",
    "select": {
        "item": "a.discovery-card", "title": ".discovery-card-title", "url": "a.discovery-card",
        "when": ".discovery-card-meta",
        "detail": {"when": ".event-date-block-content", "end": ".event-date-block-time",
                   "venue": ".location-block-name", "town": ".location-block-address",
                   "description": ".rich-text-content p.intro"},
    },
}
PAGES = {
    "https://savebuzzardsbay.org/events/bay-adventures/baysgiving-shellfishing-and-quahog-boil": "bbc_detail_baysgiving.html",
    "https://savebuzzardsbay.org/events/bay-adventures/full-moon-walks": "bbc_detail_full_moon.html",
    "https://savebuzzardsbay.org/events/bay-adventures/turkey-trot-at-the-bogs": "bbc_detail_turkey_trot.html",
}


def fake_fetch(url: str) -> str:
    key = url.rstrip("/").replace("://www.", "://")
    if key in PAGES:
        return fixture_text(PAGES[key])
    raise ConnectionError(f"no fixture for {url}")    # the other cards: an unreadable page must not sink the run


def test_helpers():
    assert last_time("3:00 PM - 6:30 PM") == time(18, 30) and last_time("Ends: 8:00pm") == time(20, 0)
    assert town_from_text("186 Onset Avenue Onset, Massachusetts 02558") == "Wareham"
    assert town_from_text("164 John Reed Rd. Westport, MA 02790") == "Westport"
    assert town_from_text("somewhere in Dartmouth") == "Dartmouth" and town_from_text("") == ""


def test_detail_pages_fill_time_venue_and_town(frozen):
    occs = HtmlConnector(BBC, cache=False).parse(fixture_text("bbc_bay_adventures.html"), fetch=fake_fetch)
    by_title = {o.title: o for o in occs}
    # Six dated cards parse; "Monthly at Horseneck Beach" and the ongoing programmes do not.
    assert len(occs) == 6
    assert "Full Moon Walks" not in by_title and "Itty Bitty Bay Adventures" not in by_title
    bays = by_title["Baysgiving Shellfishing and Quahog Boil"]
    assert bays.url.endswith("/baysgiving-shellfishing-and-quahog-boil")      # the card is the anchor
    assert (bays.start.month, bays.start.day, bays.start.time()) == (11, 12, time(15, 0))
    assert bays.end.time() == time(18, 30) and not bays.all_day
    assert bays.venue_raw == "Onset Bay Center" and bays.town == "Wareham"
    assert bays.description.startswith("Join us for a BaysGiving")
    trot = by_title["Turkey Trot at The Bogs"]
    assert (trot.start.time(), trot.end.time(), trot.venue_raw, trot.town) == (time(9, 0), time(10, 0), "The Bogs", "Mattapoisett")
    # A card whose page could not be read keeps the listing's date, all-day, no venue.
    intro = by_title["Intro to Shellfishing at North Cove"]
    assert (intro.start.month, intro.start.day, intro.all_day, intro.venue_raw, intro.town) == (11, 14, True, "", "")
