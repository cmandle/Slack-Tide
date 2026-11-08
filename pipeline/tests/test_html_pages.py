"""The html connector's page-level date, class-name times, end times and sibling grouping,
offline against saved copies of the AHA! next-night page and the Cisco Kitchen live music page."""
from datetime import time
from conftest import fixture_text
from slacktide.connectors.html import HtmlConnector, strip_trailing_time, times_from_classes
from bs4 import BeautifulSoup

AHA = {
    "id": "aha-next-aha", "kind": "html", "url": "https://ahanewbedford.org/next-aha/", "town": "New Bedford",
    "select": {
        "item": "article.elementor-post",
        "title": ".elementor-widget-theme-post-title .elementor-heading-title",
        "venue": ".elementor-widget-text-editor:not(:-soup-contains('Ends:')) .elementor-widget-container",
        "end": ".elementor-widget-text-editor:-soup-contains('Ends:')",
        "description": ".elementor-widget-theme-post-content .elementor-widget-container",
        "page_when": "h2.elementor-heading-title, h3.elementor-heading-title",
        "when_class": "tag-",
        "start": "17:00",
    },
}

CISCO = {
    "id": "cisco-live-music", "kind": "html", "url": "https://www.ciscokitchenbar.com/live-music/",
    "town": "New Bedford", "venue": "Cisco Brewers Kitchen & Bar",
    "select": {
        "item": "section.c-one-col--text:has(> h2:-soup-contains('Live Music')) p:has(> strong)",
        "group_next": 1,
        "title": "p:nth-of-type(2)",
        "when": "p",
    },
}


def test_helpers():
    assert strip_trailing_time("Day Drinkers 6pm") == "Day Drinkers"
    assert strip_trailing_time("Open Studio 5-8pm") == "Open Studio"
    assert strip_trailing_time("Artist talk at 6:30 PM") == "Artist talk"
    assert strip_trailing_time("Route 6 Walk") == "Route 6 Walk"
    node = BeautifulSoup('<article class="post tag-200pm tag-1130am tag-music"></article>', "html.parser").article
    assert times_from_classes(node, "tag-") == "2:00pm 11:30am"


def test_aha_cards_take_the_page_date_and_their_own_times(frozen):
    occs = HtmlConnector(AHA, cache=False).parse(fixture_text("aha_next_aha.html"))
    assert len(occs) >= 25
    assert {(o.start.month, o.start.day) for o in occs} == {(11, 12)}     # one night, every card
    assert all(not o.all_day for o in occs)
    park = next(o for o in occs if o.title.startswith("Create, Explore, and Collect"))
    assert park.start.time() == time(14, 0)                               # tag-200pm on the card
    assert park.end.time() == time(20, 0)                                 # "Ends: 8:00pm"
    assert "Whaling National Historical Park" in park.venue_raw
    assert "watercolor" in park.description
    assert park.url == AHA["url"]
    defaults = [o for o in occs if o.start.time() == time(17, 0)]
    assert defaults                                                       # cards without a tag open at 5
    assert all(o.end is None or o.end > o.start for o in occs)


def test_cisco_pairs_of_paragraphs(frozen):
    occs = HtmlConnector(CISCO, cache=False).parse(fixture_text("cisco_live_music.html"))
    assert len(occs) == 11
    first, last = occs[0], occs[-1]
    assert (first.title, first.start.month, first.start.day, first.start.hour) == ("Day Drinkers", 11, 5, 18)
    assert (last.title, last.start.month, last.start.day, last.start.hour) == ("Merrick Brannigan", 11, 28, 19)
    assert all(o.venue_raw == "Cisco Brewers Kitchen & Bar" and not o.all_day for o in occs)
    assert "Artist Bios" not in {o.title for o in occs} and "Matt Martin" in {o.title for o in occs}
