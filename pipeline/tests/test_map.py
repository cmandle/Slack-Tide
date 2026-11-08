"""The Map view and the venues file behind it: alias-aware venue canonicalisation, the place
join with its town-centre fallback, and the page. Runs offline against a small events.json."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from slacktide import build, config
from slacktide.normalize import VenueCanon, venue_key, venue_aliases

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)

VENUES = [
    {"id": "gallery-x", "name": "Gallery X", "town": "New Bedford", "address": "169 William St, New Bedford, MA 02740",
     "lat": 41.63513, "lon": -70.92886, "url": "https://galleryx.org/", "aliases": ["Gallery X, Inc"]},
    {"id": "the-z", "name": "The Zeiterion", "town": "New Bedford", "lat": 41.633, "lon": -70.9255,
     "aliases": ["Zeiterion Performing Arts Center", "Speakeasy @ The Z! - 984 Purchase St"]},
    {"id": "no-coords", "name": "Dike Creek Reserve", "town": "Dartmouth"},
]


def series(title, start, venue, town, category="Music", approval="approved", cadence="once", count=1):
    occ = [{"start": (start + timedelta(days=7 * i)).isoformat(), "end": None, "all_day": False} for i in range(count)]
    return {"id": title.lower().replace(" ", "-"), "title": title, "venue": venue, "town": town, "category": category,
            "source_id": "aha-next-aha", "url": "https://example.org/" + title, "cost": "", "first_start": occ[0]["start"],
            "last_start": occ[-1]["start"], "count": count, "cadence": cadence, "weekday": None, "occurrences": occ,
            "summary": "", "approval": approval, "decided_by": ""}


def test_venue_key_drops_a_street_address_and_aliases_win():
    assert venue_key("Gallery X 169 William Street") == venue_key("Gallery X") == "gallery x"
    assert venue_key("New Bedford Art Museum, 608 Pleasant St.") == "new bedford art museum"
    assert venue_key("Speakeasy @ The Z! - 984 Purchase St") == "speakeasy the z"
    assert venue_key("Sangha Yoga New Bedford 693 Purchase Street at the corner of Spring Street dNB") == "sangha yoga"
    assert venue_key("1265 Purchase Street") == "1265 purchase street"      # a bare address keeps its key
    assert venue_key("Narrows Center For The Arts Fall River MA") == "narrows center for the arts"
    table = venue_aliases(VENUES)
    assert table["gallery x"] == "Gallery X" and table["speakeasy the z"] == "The Zeiterion"   # ", Inc" was already stripped
    canon = VenueCanon(table)
    assert canon.resolve("Gallery X 169 William Street") == "Gallery X"           # the address form lands on the entry
    assert canon.resolve("Zeiterion Performing Arts Center") == "The Zeiterion"   # an alias, not first-seen spelling
    assert canon.resolve("Somewhere Else, 5 Main St.") == "Somewhere Else, 5 Main St."   # unknown: raw, as before
    assert canon.resolve("Somewhere Else") == "Somewhere Else, 5 Main St."       # ...and its address form merges with it


def test_map_places_joins_venues_and_falls_back_to_town_centres():
    today = NOW.replace(hour=0, minute=0)
    rows = [
        series("Opening", today + timedelta(days=1, hours=18), "Gallery X 169 William Street", "New Bedford", "Arts & Theatre"),
        series("Cabaret", today + timedelta(days=2, hours=20), "Speakeasy @ The Z! - 984 Purchase St", "New Bedford"),
        series("Concert", today + timedelta(days=3, hours=19), "The Zeiterion", "New Bedford", count=5, cadence="weekly"),
        series("Unknown bar gig", today + timedelta(days=1, hours=21), "Some Bar, 9 Water St.", "New Bedford"),
        series("Reserve walk", today + timedelta(days=4, hours=9), "Dike Creek Reserve", "Dartmouth", "Outdoors & Nature"),
        series("No venue walk", today + timedelta(days=5, hours=9), "", "Dartmouth", "Outdoors & Nature"),
        series("Nowhere", today + timedelta(days=5, hours=9), "", ""),
        series("Over", today - timedelta(days=5), "Gallery X", "New Bedford"),
        series("Pending", today + timedelta(days=1), "Gallery X", "New Bedford", approval="pending"),
    ]
    places, unplaced = build.map_places(build.published(rows), VENUES, NOW)
    assert unplaced == 1                                    # "Nowhere": no venue, no town
    by_id = {p["id"]: p for p in places}
    assert [p["id"] for p in places] == ["gallery-x", "the-z", "town-new-bedford", "town-dartmouth"]   # town order, pinned before approximate
    assert [r["series"]["title"] for r in by_id["gallery-x"]["rows"]] == ["Opening"]                    # the past series is gone
    assert [r["series"]["title"] for r in by_id["the-z"]["rows"]] == ["Cabaret", "Concert"]             # two spellings, one pin
    assert by_id["the-z"]["family"] == "music" and by_id["gallery-x"]["family"] == "arts"
    assert by_id["town-new-bedford"]["approx"] and (by_id["town-new-bedford"]["lat"], by_id["town-new-bedford"]["lon"]) == config.TOWN_CENTERS["New Bedford"]
    assert [r["series"]["title"] for r in by_id["town-dartmouth"]["rows"]] == ["Reserve walk", "No venue walk"]   # known venue without coordinates, and no venue
    assert by_id["gallery-x"]["address"].startswith("169 William St") and by_id["gallery-x"]["url"] == "https://galleryx.org/"


def test_map_page_renders_places_and_pins(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "load_venues", lambda path=None: VENUES)
    today = NOW.replace(hour=0, minute=0)
    rows = [series("Opening", today + timedelta(days=1, hours=18), "Gallery X 169 William Street", "New Bedford", "Arts & Theatre"),
            series("Concert", today + timedelta(days=3, hours=19), "The Zeiterion", "New Bedford", count=5, cadence="weekly"),
            series("Reserve walk", today + timedelta(days=4, hours=9), "Dike Creek Reserve", "Dartmouth", "Outdoors & Nature")]
    (tmp_path / "events.json").write_text(json.dumps({"generated_at": NOW.isoformat(), "series_count": 3, "occurrence_count": 7, "series": rows}), encoding="utf-8")
    out = tmp_path / "site"
    build.build(tmp_path, out, now=NOW)
    html = (out / "map" / "index.html").read_text(encoding="utf-8")
    assert "is coming" not in html and "<h1>Map</h1>" in html
    assert "2 places · 3 listings · 2 towns" in html                     # pinned places in the dateline; the approximate one is not a place
    assert 'href="../map/" aria-current="page"' in html                  # the Map button pressed
    assert html.count('class="place"') == 3 and 'id="place-gallery-x"' in html and 'id="place-town-dartmouth"' in html
    assert 'data-lat="41.63513" data-lon="-70.92886" data-approx="0"' in html
    assert f'data-lat="{config.TOWN_CENTERS["Dartmouth"][0]:.5f}"' in html and 'data-approx="1"' in html
    assert "Town center, exact places to come" in html and '<span class="pe-venue">Dike Creek Reserve</span>' in html
    assert '<a href="https://galleryx.org/" rel="noopener" target="_blank">Gallery X</a>' in html
    assert '<div class="place-addr">169 William St, New Bedford, MA 02740</div>' in html
    assert 'data-cats="arts" data-family="arts"' in html and 'style="--cat: var(--st-cat-music)"' in html
    assert "THU JAN 1 · 6:00 PM" in html and "SAT JAN 3 · 7:00 PM · weekly" in html   # NOW is Wed Dec 31 2098
    assert 'data-tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png"' in html and "openstreetmap.org/copyright" in html
    assert 'assets/vendor/leaflet/leaflet.css' in html and 'assets/map.js' in html
    assert html.index("vendor/leaflet/leaflet.css") < html.index("assets/site.css")   # the site's rules win
    scripts = [m for m in html.split('<script src="../assets/')[1:]]
    assert [s.split("?")[0] for s in scripts] == ["vendor/leaflet/leaflet.js", "site.js", "map.js"]   # the library first, then the filters, then the map
    for a in ("map.js", "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/leaflet/LICENSE"):
        assert (out / "assets" / a).exists()
    assert "—" not in html


def test_venues_file_is_well_formed():
    venues = config.load_venues()
    assert len(venues) >= 30
    ids = [v["id"] for v in venues]
    names = [v["name"].lower() for v in venues]
    assert len(set(ids)) == len(ids) and len(set(names)) == len(names)
    (s, w), (n, e) = build.MAP_BOUNDS
    for v in venues:
        assert v["town"] in config.TOWNS, v["id"]
        assert "—" not in v["name"]
        if v.get("lat") is not None:
            assert s <= float(v["lat"]) <= n and w <= float(v["lon"]) <= e, v["id"]
            assert v.get("geocoded"), v["id"]
    # Names of venues with approved series are hashed into their ids; these must not drift.
    assert {"The Zeiterion", "DNRT Center @ Helfand Farm", "Destruction Brook Woods", "Dike Creek Reserve",
            "Ocean View Farm", "Russells Mills Woods", "Smith Farm", "Wernick Farm"} <= {v["name"] for v in venues}
    for t in config.TOWNS:
        assert t in config.TOWN_CENTERS
