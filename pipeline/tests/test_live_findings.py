"""Regression tests for what the first live run (2026-10-11) got wrong."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from slacktide.models import Occurrence
from slacktide.normalize import clean_text, normalize, resolve_town, classify, is_closure
from slacktide.connectors.ical import split_location
from slacktide.series import title_key, collapse
from slacktide.reconcile import reconcile

TZ = ZoneInfo("America/New_York")

def occ(title, start, venue="Narrows Center for the Arts", source="viva", town="Fall River", uid=None, **kw):
    return Occurrence(source_id=source, source_uid=uid or title + start.isoformat(), title=title,
                      start=start, end=None, all_day=False, venue_raw=venue, town=town, url="", **kw)

def test_clean_text_strips_html_and_normalises_quotes():
    assert clean_text("<p>Dining Room</p> - Tiverton RI 02878") == "Dining Room - Tiverton RI 02878"
    assert clean_text("Paul’s “Nosferatu” Live") == "Paul's \"Nosferatu\" Live"
    assert clean_text("Rotch-Jones-Duff House &amp; Garden Museum") == "Rotch-Jones-Duff House & Garden Museum"

def test_html_in_description_does_not_classify_as_class():
    desc = '<p>An evening of song.</p> <span class="tribe-events">Doors 7pm</span>'
    assert classify("Dar Williams", "Narrows Center for the Arts", desc) != "Education & Workshops"
    assert classify("Printmaking Class", "", "") == "Arts & Theatre"
    assert classify("Budgeting 101: Workshop Series", "", "") == "Education & Workshops"

def test_split_location_civicplus_shapes():
    assert split_location("<p>Dining Room</p> - Tiverton RI 02878") == ("", "Dining Room")
    assert split_location("- 34 Roosevelt Avenue Tiverton RI 02878") == ("34 Roosevelt Avenue Tiverton RI 02878", "")
    assert split_location("<p>Council on Aging, Rm. #2</p> - 115 Wood St Somerset MA 02726") == ("115 Wood St Somerset MA 02726", "Council on Aging, Rm. #2")
    assert split_location("Tiverton Senior Center") == ("Tiverton Senior Center", "")
    assert split_location('<p>VIA ZOOM</p><p><a href="https://x">link</a></p>') == ("VIA ZOOM link", "")
    assert split_location("") == ("", "")

def test_closures_and_election_admin_dropped():
    for t in ("Library Closed", "Eary Voting", "Last Day to Register to Vote",
              "Advanced Processing for November 3rd State Election", "Town Hall Closed - Columbus Day"):
        assert is_closure(t), t
    for t in ("Bingo!", "Open Mic Night", "Election of Officers Dinner"):
        assert not is_closure(t), t
    now = datetime(2098, 12, 31, 12, tzinfo=TZ)
    occs = [occ("Library Closed", now, venue="", source="brownell", town="Little Compton", uid="a"),
            occ("Knitting Group", now, venue="", source="brownell", town="Little Compton", uid="b")]
    normalize(occs, {"brownell": "Little Compton"}, {"brownell": "Brownell Library"})
    assert occs[0].dropped == "closure"
    assert occs[1].dropped == "" and occs[1].venue == "Brownell Library"

def test_town_inferred_from_venue_when_city_missing():
    assert resolve_town("", "Fall River", hint="New Bedford Whaling Museum") == "New Bedford"
    assert resolve_town("", "Fall River", hint="Narrows Center for the Arts") == "Fall River"
    assert resolve_town("Fall River", "Dartmouth", hint="New Bedford Whaling Museum") == "Fall River"

def test_title_key_ignores_town_date_and_cadence_suffixes():
    assert title_key("Eric Lindell - Fall River") == title_key("Eric Lindell")
    assert title_key("Peter Wolf and The Midnight Travelers - Friday, Nov. 20") == "peter wolf and the midnight travelers"
    assert title_key("Half Priced Food (weekly)") == "half priced food"
    assert title_key("Joan Osborne Sings The Songs of Bob Dylan - Fall River") == title_key("Joan Osborne Sings the Songs of Bob Dylan")

def test_near_duplicate_listings_merge_and_venue_suffix_canonicalises():
    now = datetime(2098, 12, 31, 20, tzinfo=TZ)
    occs = [occ("Robbie Fulks & Heather Maloney - Fall River", now, uid="a"),
            occ("Robbie Fulks & Heath Maloney", now, uid="b"),
            occ("Falco and Book Play Jerry Garcia", now + timedelta(days=7), uid="c"),
            occ("Falco and Book Play Jerry Garcia - Fall River", now + timedelta(days=7), uid="d",
                venue="Narrows Center For The Arts Fall River MA"),
            occ("Chris Smither", now + timedelta(days=14), uid="e")]
    normalize(occs, {"viva": "Fall River"})
    assert len({o.venue for o in occs}) == 1, {o.venue for o in occs}
    series = collapse(occs)
    titles = sorted(s.title for s in series)
    assert titles == ["Chris Smither", "Falco and Book Play Jerry Garcia", "Robbie Fulks & Heath Maloney"], titles
    assert all(s.count == 1 for s in series)

def test_all_day_copy_of_a_timed_listing_is_dropped_and_two_sittings_are_once():
    day = datetime(2098, 12, 31, 0, 0, tzinfo=TZ)
    occs = [occ("Joan Osborne Sings the Songs of Bob Dylan", day, uid="a"),
            occ("Joan Osborne Sings The Songs of Bob Dylan - Fall River", day.replace(hour=20), uid="b"),
            occ("All the Genres Book Club", day.replace(hour=16), venue="Brownell Library", source="brownell", town="Little Compton", uid="c"),
            occ("All the Genres Book Club", day.replace(hour=18), venue="Brownell Library", source="brownell", town="Little Compton", uid="d")]
    occs[0].all_day = True
    normalize(occs, {})
    by = {s.title: s for s in collapse(occs)}
    joan = by["Joan Osborne Sings the Songs of Bob Dylan"]
    assert joan.count == 1 and joan.cadence == "once" and joan.occurrences[0]["start"].endswith("T20:00:00-05:00")
    club = by["All the Genres Book Club"]
    assert club.count == 2 and club.cadence == "once"

def test_distinct_shows_at_same_venue_do_not_merge():
    now = datetime(2098, 12, 31, 20, tzinfo=TZ)
    occs = [occ("Neal McCarthy Electric Band", now, uid="a"),
            occ("Neal McCarthy Electric Band", now + timedelta(days=30), uid="b"),
            occ("Neal McCarthy Acoustic", now + timedelta(days=3), uid="c")]
    normalize(occs, {"viva": "Fall River"})
    series = collapse(occs)
    assert sorted((s.title, s.count) for s in series) == [("Neal McCarthy Acoustic", 1), ("Neal McCarthy Electric Band", 2)]

def test_weekend_and_weekday_cadences():
    sat = datetime(2099, 1, 3, 10, tzinfo=TZ)  # a Saturday
    brunch = [occ("Weekend Brunch", sat + timedelta(days=d), venue="Tipsy Toboggan", uid=str(d))
              for w in range(4) for d in (7 * w, 7 * w + 1)]
    mon = datetime(2099, 1, 5, 9, tzinfo=TZ)   # a Monday
    fitness = [occ("Functional Fitness", mon + timedelta(days=d), venue="", source="tiv", town="Tiverton", uid=str(d))
               for w in range(3) for d in range(7 * w, 7 * w + 5)]
    tue = datetime(2099, 1, 6, 18, tzinfo=TZ)  # a Tuesday
    yoga = [occ("Free All Levels Yoga", tue + timedelta(days=d), venue="First Congregational Church", uid=str(d))
            for w in range(4) for d in (7 * w, 7 * w + 2)]
    normalize(brunch, {"viva": "Fall River"}); normalize(fitness, {"tiv": "Tiverton"}); normalize(yoga, {"viva": "Fall River"})
    assert collapse(brunch)[0].cadence == "weekends"
    assert collapse(fitness)[0].cadence == "weekdays"
    assert collapse(yoga)[0].cadence == "several-a-week"   # Tuesday and Thursday, not "daily"

def test_committees_and_commissions_are_civic():
    for t in ("Cemetery Commission Meeting", "Community Preservation Committee", "Board of Public Works Meeting",
              "Somerset Board of Water & Sewer Commissioners", "Probate Court", "Technical Review Committee"):
        assert classify(t, "", "") == "Civic & Town Meetings", t

def test_reconcile_requires_same_town_and_groups_missed():
    now = datetime(2098, 12, 31, 21, tzinfo=TZ)
    check = [occ("Karaoke Nights!", now + timedelta(days=d), venue="The Gallery Bar", source="explore", town="New Bedford", uid=f"k{d}")
             for d in range(0, 21, 7)]
    check.append(occ("Boo at the Zoo", now, venue="Buttonwood Park Zoo", source="explore", town="New Bedford", uid="z"))
    primary = [occ("Karaoke Nights", now, venue="Some Bar", source="viva", town="Fall River", uid="p1"),
               occ("Karaoke Nights", now + timedelta(days=7), venue="The Gallery Bar", source="nb", town="New Bedford", uid="p2"),
               occ("Fall River Farmers Market", now, venue="NoMa", source="viva", town="Fall River", uid="p3"),
               occ("Walking Tour", now, venue="Whaling Museum", source="nb", town="New Bedford", uid="p4")]
    normalize(check, {}); normalize(primary, {})
    r = reconcile(primary, check)
    assert r["check_matched"] == 1 and r["check_total"] == 4   # three karaoke rows plus the zoo
    assert r["check_missed_series"] == 2
    assert r["check_missed"][0]["title"] == "Karaoke Nights!" and r["check_missed"][0]["rows"] == 2
    assert r["check_towns"] == ["New Bedford"]
    # Only the Walking Tour counts: Fall River rows are outside the check source's towns.
    assert r["primary_only_count"] == 1 and r["primary_only_series"] == 1
