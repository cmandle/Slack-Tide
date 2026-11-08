"""The Squarespace events collection connector, offline against the Girls Walk schedule JSON."""
from datetime import timedelta
import pytest
from conftest import fixture_text
from slacktide.connectors.squarespace import SquarespaceConnector

SRC = {"id": "south-coast-girls-walk", "kind": "squarespace", "url": "https://www.southcoastgirlswalk.com/our-schedule", "town": ""}


def test_parse_reads_upcoming_and_past_items(frozen):
    occs = SquarespaceConnector(SRC, cache=False).parse(fixture_text("squarespace_girls_walk.json"))
    assert len(occs) == 6 and occs == sorted(occs, key=lambda o: o.start)
    by_title = {o.title: o for o in occs}
    walk = by_title["Daydreaming of Summer"]                  # trailing space in the source title is gone
    assert walk.start.isoformat() == "2026-11-15T10:00:00-05:00" and walk.end - walk.start == timedelta(hours=1)
    assert walk.url == "https://www.southcoastgirlswalk.com/our-schedule/daydreaming-of-summer"
    assert walk.venue_raw == "" and walk.town == ""           # the site leaves the location block empty
    assert walk.description.startswith("While we are loving") and "<" not in walk.description
    assert not walk.all_day and walk.source_uid
    assert by_title["Sunrise Stroll"].start.hour == 7          # 12:00Z is 7am Eastern in November
    assert by_title["Cemetery Stroll - Swansea"].start.month == 10


def test_a_location_block_gives_venue_and_town(frozen):
    text = fixture_text("squarespace_girls_walk.json").replace(
        '"addressTitle": ""', '"addressTitle": "Horseneck Beach"', 1).replace(
        '"addressLine2": ""', '"addressLine2": "Westport, MA 02790"', 1)
    occs = SquarespaceConnector(SRC, cache=False).parse(text)
    first = [o for o in occs if o.venue_raw][0]
    assert (first.venue_raw, first.town) == ("Horseneck Beach", "Westport")


def test_not_a_collection_fails_loudly(frozen):
    with pytest.raises(ValueError):
        SquarespaceConnector(SRC, cache=False).parse('{"website": {}}')
