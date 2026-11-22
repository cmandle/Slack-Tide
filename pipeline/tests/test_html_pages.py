"""The html connector's page-level date, class-name times, end times and sibling grouping,
offline against saved copies of the AHA! next-night page and the Cisco Kitchen live music page."""
from datetime import time
from conftest import fixture_text
from slacktide.connectors.html import HtmlConnector, setting_time, strip_trailing_time, times_from_classes
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
        "item": ":is(section, div):has(> h2:-soup-contains('Live Music')) > p:has(> strong)",
        "group_next": 1,
        "title": "p:nth-of-type(2)",
        "when": "p",
        "start": "18:00",
    },
}


def test_helpers():
    assert strip_trailing_time("Day Drinkers 6pm") == "Day Drinkers"
    assert strip_trailing_time("Open Studio 5-8pm") == "Open Studio"
    assert strip_trailing_time("Artist talk at 6:30 PM") == "Artist talk"
    assert strip_trailing_time("Route 6 Walk") == "Route 6 Walk"
    node = BeautifulSoup('<article class="post tag-200pm tag-1130am tag-music"></article>', "html.parser").article
    assert times_from_classes(node, "tag-") == "2:00pm 11:30am"
    assert setting_time("17:00") == time(17, 0) and setting_time("6pm") == time(18, 0) and setting_time("") is None


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
    """The 2026-11-22 page: the pairs sit in the left column of a two-column section, three
    "Day Drinkers Music Thursdays" carry no time and take the source's default start."""
    occs = HtmlConnector(CISCO, cache=False).parse(fixture_text("cisco_live_music.html"))
    assert len(occs) == 21
    first, last = occs[0], occs[-1]
    assert (first.title, first.start.month, first.start.day, first.start.hour) == ("Day Drinkers", 11, 19, 18)
    assert (last.title[:12], last.start.month, last.start.day, last.start.hour) == ("Bob Jennings", 12, 27, 10)
    assert all(o.venue_raw == "Cisco Brewers Kitchen & Bar" and not o.all_day for o in occs)
    thursdays = [o for o in occs if o.title == "Day Drinkers Music Thursdays"]
    assert [(o.start.day, o.start.hour) for o in thursdays] == [(3, 18), (10, 18), (17, 18)]
    titles = {o.title for o in occs}
    assert "Matt Martin" in titles and "Jon Tyler" in titles                       # a leading nbsp is stripped
    assert "Artist Bios" not in titles and "A Celtic Christmas with Pourmen" not in titles   # the other column


def test_cisco_old_one_column_layout(frozen):
    """The selector still reads the 2026-11-08 layout, the heading a direct child of the section."""
    page = """<section class="c-one-col--text"><h2>Indoor Live Music </h2>
    <p><strong>Thursday, November 5 </strong></p><p>Day Drinkers 6pm</p><p><br/></p>
    <p><strong>Friday, November 6 </strong></p><p>Ian Stackpole 7pm</p></section>
    <section class="c-one-col--text"><h2>Artist Bios</h2><p>Day Drinkers</p><p>Bio <strong>#tag</strong></p></section>"""
    occs = HtmlConnector(CISCO, cache=False).parse(page)
    assert [(o.title, o.start.day, o.start.hour) for o in occs] == [("Day Drinkers", 5, 18), ("Ian Stackpole", 6, 19)]
