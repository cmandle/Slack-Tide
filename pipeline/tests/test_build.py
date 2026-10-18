"""The site generator: selection rules, configuration-driven lists, the tide panel's three states,
and the placeholder pages. Runs offline against a small events.json written by the test."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
from conftest import fixture_text
from slacktide import config, build, tide

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)   # a Wednesday

def series(title, starts, town="Fall River", category="Music", cadence="once", source="viva-fall-river", all_day=False, sid=None):
    occ = [{"start": s.isoformat(), "end": (s + timedelta(hours=2)).isoformat(), "all_day": all_day} for s in starts]
    return {"id": sid or title.lower().replace(" ", "-"), "title": title, "venue": "Narrows Center for the Arts",
            "town": town, "category": category, "source_id": source, "url": "https://example.org/" + title,
            "cost": "", "first_start": occ[0]["start"], "last_start": occ[-1]["start"], "count": len(occ),
            "cadence": cadence, "weekday": None, "occurrences": occ}

@pytest.fixture
def data(tmp_path):
    today = NOW.replace(hour=0, minute=0)
    rows = [
        series("Tonight gig", [today.replace(hour=19, minute=30)]),
        series("Already over", [today.replace(hour=8)]),
        series("Weekly bingo", [today - timedelta(days=5), today + timedelta(days=2, hours=18), today + timedelta(days=9, hours=18)],
               town="Tiverton", category="Sports & Recreation", cadence="weekly", source="town-tiverton"),
        series("Next weekend fair", [today + timedelta(days=4)], town="Dartmouth", category="Markets & Fairs", all_day=True, source="dnrt"),
        series("Too far out", [today + timedelta(days=8)]),
        series("Unclassified talk", [today + timedelta(days=1, hours=10)], category="", town="Little Compton", source="brownell-library"),
    ]
    payload = {"generated_at": NOW.isoformat(), "series_count": len(rows), "occurrence_count": sum(r["count"] for r in rows), "series": rows}
    (tmp_path / "events.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path

def test_select_tonight_and_week(data):
    events = build.load_events(data / "events.json")
    tonight, week = build.select(events["series"], NOW)
    assert [r["series"]["title"] for r in tonight] == ["Tonight gig"]
    titles = {d: [r["series"]["title"] for r in rows] for d, rows in week.items() if rows}
    assert len(week) == 7 and set(sum(titles.values(), [])) == {"Weekly bingo", "Next weekend fair", "Unclassified talk"}
    bingo_day = next(d for d, t in titles.items() if "Weekly bingo" in t)
    assert bingo_day == (NOW + timedelta(days=2)).date()   # the next occurrence, not the past one, and only once

def test_build_writes_pages_and_reads_config(data, tmp_path):
    out = tmp_path / "site"
    r = build.build(data, out, now=NOW)
    assert r["tonight"] == 1 and r["week"] == 3 and r["tide"] == "unavailable"
    html = (out / "index.html").read_text(encoding="utf-8")
    for t in config.TOWNS:
        assert f'value="{t}"' in html
    for fam in config.CATEGORY_FAMILIES:          # one tile per display family, from configuration
        assert f'class="tile" type="button" data-cat="{fam}"' in html
    assert set(config.CATEGORY_FAMILY_OF) == set(config.CATEGORIES)   # every taxonomy entry has a family
    assert 'data-cat="outdoors" data-category="Sports &amp; Recreation"' in html   # bingo is Sports, family Outdoors
    assert html.count('class="card"') == 1 and html.count('class="week-row"') == 3
    assert 'data-source="viva-fall-river"' in html and 'class="card-prov" title="Viva Fall River">Read by a person' in html
    assert "Tide data unavailable" in html and 'data-state="unavailable"' in html
    assert "Too far out" not in html and "Already over" not in html
    assert "FRI 2 · 6P" in html and "FRI 2 · 6:00 PM" in html   # phone and desktop forms of the when column
    assert "Archivo" in html and 'href="calendar/"' in html and 'href="map/"' in html
    assert 'id="week-empty" hidden' in html and 'id="tonight-empty" hidden' in html   # both lists have rows
    for sub in ("groups", "volunteer", "calendar", "map", "add"):
        p = out / sub / "index.html"
        assert p.exists() and "is coming" in p.read_text(encoding="utf-8")
    for a in ("tokens.css", "site.css", "site.js"):
        assert (out / "assets" / a).exists()
    assert "—" not in html   # no em dashes in public copy

def test_tide_parse_and_freshness(tmp_path):
    hilo = tide.parse_predictions(fixture_text("coops_hilo.json"))
    assert hilo[0] == {"t": "2098-12-31 01:57", "v": 3.37, "type": "H"} and len(hilo) == 8
    with pytest.raises(RuntimeError):
        tide.parse_predictions('{"error": {"message": "No Predictions data was found."}}')
    fresh = datetime(2098, 12, 31, 16, 0, tzinfo=timezone.utc)
    payload = {"station": "8447386", "station_name": "Fall River", "datum": "MLLW", "units": "ft",
               "fetched_at": fresh.isoformat(), "hilo": hilo,
               "levels": [{"t": "2098-12-31 11:30", "v": 2.1}, {"t": "2098-12-31 12:00", "v": 2.6}, {"t": "2098-12-31 12:30", "v": 3.0}]}
    p = tide.write(payload, tmp_path)
    assert tide.load(p, now=fresh + timedelta(hours=23)) is not None
    assert tide.load(p, now=fresh + timedelta(hours=25)) is None
    assert tide.load(tmp_path / "missing.json") is None

def test_tide_panel_renders_staff_and_readings(data, tmp_path):
    hilo = tide.parse_predictions(fixture_text("coops_hilo.json"))
    payload = {"station": "8447386", "station_name": "Fall River", "datum": "MLLW", "units": "ft",
               "fetched_at": NOW.astimezone(timezone.utc).isoformat(), "hilo": hilo,
               "levels": [{"t": "2098-12-31 11:30", "v": 2.1}, {"t": "2098-12-31 12:00", "v": 2.6}, {"t": "2098-12-31 12:30", "v": 3.0}]}
    tide.write(payload, data)
    r = build.build(data, tmp_path / "site", now=NOW)
    assert r["tide"] == "ok"
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'class="tide-staff"' in html and "2.6 ft ↑<span class=long> rising</span>" in html
    assert "High 2:21 PM" in html and "Low 8:01 PM" in html      # the next high and low after noon
    assert 'id="tide-data"' in html
