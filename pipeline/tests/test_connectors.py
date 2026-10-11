from conftest import fixture_text
from slacktide.connectors.tribe import TribeConnector, parse_json
from slacktide.connectors.ical import ICalConnector

def test_parse_json_skips_php_warnings():
    d = parse_json(fixture_text("tribe_buzzards.txt"))
    assert d["total"] == 4 and len(d["events"]) == 4

def test_tribe_connector_reads_fixture(frozen, monkeypatch):
    c = TribeConnector({"id": "bb", "kind": "tribe", "url": "x", "town": "Westport"}, cache=False)
    monkeypatch.setattr(c, "fetch_text", lambda url, params=None, timeout=30: fixture_text("tribe_buzzards.txt"))
    occs = c.fetch()
    assert len(occs) == 4
    assert occs[0].town == "Westport" and occs[0].start.tzinfo is not None

def test_ical_drops_nothing_itself_but_parses_all_day(frozen):
    c = ICalConnector({"id": "tiv", "kind": "ical", "url": "x", "town": "Tiverton"}, cache=False)
    occs = c.parse(fixture_text("civicplus.ics"))
    titles = [o.title for o in occs]
    assert "New Year's Day" in titles and "Bingo!" in titles
    nyd = next(o for o in occs if o.title == "New Year's Day")
    assert nyd.all_day is True
