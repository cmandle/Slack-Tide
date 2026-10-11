from conftest import fixture_text
from slacktide.connectors.tribe import TribeConnector
from slacktide.connectors.ical import ICalConnector
from slacktide.normalize import normalize, VenueCanon, resolve_town, classify
from slacktide.series import collapse
from slacktide.reconcile import reconcile

def _explore(frozen, monkeypatch):
    c = TribeConnector({"id": "explore", "kind": "tribe", "url": "x", "town": "New Bedford"}, cache=False)
    monkeypatch.setattr(c, "fetch_text", lambda url, params=None, timeout=30: fixture_text("tribe_explore.json"))
    occs = c.fetch(); normalize(occs, {"explore": "New Bedford"}); return occs

def test_entities_decoded_and_venues_canonicalised(frozen, monkeypatch):
    occs = _explore(frozen, monkeypatch)
    venues = {o.venue for o in occs}
    assert "Rotch-Jones-Duff House & Garden Museum" in venues
    assert sum(1 for v in venues if v.lower().startswith(("gallery x",))) == 1, venues
    assert sum(1 for v in venues if "unitarian" in v.lower()) == 1, venues

def test_zip_and_trailing_period_resolve_to_town(frozen, monkeypatch):
    occs = _explore(frozen, monkeypatch)
    assert all(o.town == "New Bedford" for o in occs)
    assert resolve_town("02740", "") == "New Bedford"
    assert resolve_town("New Bedford.", "") == "New Bedford"
    assert resolve_town("South Dartmouth", "") == "Dartmouth"

def test_source_categories_ignored_and_rules_classify(frozen, monkeypatch):
    occs = _explore(frozen, monkeypatch)
    by = {o.title: o.category for o in occs}
    assert by["Shakespeare in New Bedford: Hamlet"] == "Arts & Theatre"
    assert by["Octave Avenue Open Mic"] == "Music"
    assert by["Harbour walk: winter birds"] == "Outdoors & Nature"
    assert "Free" not in set(by.values()) and "Downtown" not in set(by.values())

def test_series_collapse_weekly_and_once(frozen, monkeypatch):
    occs = _explore(frozen, monkeypatch)
    series = collapse(occs)
    hamlet = next(s for s in series if "Hamlet" in s.title)
    assert hamlet.count == 3 and hamlet.cadence == "daily"
    once = [s for s in series if s.cadence == "once"]
    assert len(once) >= 4

def test_holidays_dropped_and_bingo_weekly(frozen):
    c = ICalConnector({"id": "tiv", "kind": "ical", "url": "x", "town": "Tiverton"}, cache=False)
    occs = c.parse(fixture_text("civicplus.ics")); normalize(occs, {"tiv": "Tiverton"})
    dropped = {o.title for o in occs if o.dropped}
    assert dropped == {"New Year's Day", "Early Voting"}
    series = collapse(occs)
    bingo = next(s for s in series if s.title == "Bingo!")
    assert bingo.cadence == "weekly" and bingo.count == 3 and bingo.weekday == 0
    council = next(s for s in series if "Council" in s.title)
    assert council.category == "Civic & Town Meetings"

def test_reconcile_counts(frozen, monkeypatch):
    check = _explore(frozen, monkeypatch)
    primary = [o for o in check if "Hamlet" in o.title][:2]
    r = reconcile(primary, check)
    assert r["check_matched"] == 2 and r["check_missed_rows"] == 7 and r["primary_only_count"] == 0
    assert r["check_missed_series"] == len(r["check_missed"]) <= 7
