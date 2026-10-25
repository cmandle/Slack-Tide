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

def series(title, starts, town="Fall River", category="Music", cadence="once", source="viva-fall-river", all_day=False, sid=None, approval="approved"):
    occ = [{"start": s.isoformat(), "end": (s + timedelta(hours=2)).isoformat(), "all_day": all_day} for s in starts]
    return {"id": sid or title.lower().replace(" ", "-"), "title": title, "venue": "Narrows Center for the Arts",
            "town": town, "category": category, "source_id": source, "url": "https://example.org/" + title,
            "cost": "", "first_start": occ[0]["start"], "last_start": occ[-1]["start"], "count": len(occ),
            "cadence": cadence, "weekday": None, "occurrences": occ, "summary": "", "approval": approval, "decided_by": ""}

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
        series("Waiting for review", [today + timedelta(days=2, hours=20)], town="New Bedford", source="zeiterion", approval="pending"),
        series("Rejected gig", [today.replace(hour=21)], town="New Bedford", source="zeiterion", approval="rejected"),
    ]
    payload = {"generated_at": NOW.isoformat(), "series_count": len(rows), "occurrence_count": sum(r["count"] for r in rows), "series": rows}
    (tmp_path / "events.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path

def test_select_tonight_and_week(data):
    events = build.load_events(data / "events.json")
    tonight, week = build.select(build.published(events["series"]), NOW)
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
    assert html.count('class="card"') == 1 and html.count('class="week-card"') == 3 and 'class="week-grid"' in html
    assert 'id="category"' in html and 'id="section"' in html   # the category and section selects
    assert '<option value="music">Music</option>' in html and '<option value="" selected>Events</option>' in html
    assert '<option value="groups/">Community groups &amp; meetups</option>' in html
    assert 'data-source="viva-fall-river"' in html and 'class="card-prov" title="Viva Fall River">Read by a person' in html
    assert "Tide data unavailable" in html and 'data-state="unavailable"' in html
    assert "Too far out" not in html and "Already over" not in html
    assert "Waiting for review" not in html and "Rejected gig" not in html   # decision 11: only approved series publish
    assert r["published"] == 6 and r["pending"] == 1
    # The week card: date cell, time, place, town chip and the category band, in start order.
    assert '<span class="wk-day">FRI JAN 2</span><span class="wk-time">6:00 PM</span>' in html   # NOW is Dec 31, the week is January
    assert '<span class="wk-chip">Tiverton</span>' in html and '<span class="wk-band" title="Sports &amp; Recreation">Outdoors</span>' in html
    assert '<span class="wk-time">All day</span>' in html
    assert '<span class="wk-day">SUN JAN 4</span>' in html   # the month joins the day across the month boundary
    order = [m for m in ("Unclassified talk", "Weekly bingo", "Next weekend fair") if m in html]
    assert [html.index(t) for t in order] == sorted(html.index(t) for t in order)
    assert "Archivo" in html and 'href="calendar/"' in html and 'href="map/"' in html
    assert 'id="week-empty" hidden' in html and 'id="tonight-empty" hidden' in html   # both lists have rows
    for sub in ("groups", "volunteer", "map"):
        p = out / sub / "index.html"
        assert p.exists() and "is coming" in p.read_text(encoding="utf-8")
    # The calendar: this month at calendar/, the next two months the window touches at calendar/YYYY-MM/.
    cal = (out / "calendar" / "index.html").read_text(encoding="utf-8")
    assert "<h1>December 2098</h1>" in cal and 'data-date="2098-12-31" data-today' in cal
    assert cal.count('class="cal-day"') == 35 and 'data-date="2098-11-30" data-outside' in cal   # Dec 1 2098 is a Monday; Sunday-first, padded to whole weeks
    assert '<a class="btn" href="../calendar/2099-01/">January →</a>' in cal and '<span class="btn is-off">← </span>' in cal
    assert (out / "calendar" / "2099-01" / "index.html").exists() and (out / "calendar" / "2099-02" / "index.html").exists()
    jan = (out / "calendar" / "2099-01" / "index.html").read_text(encoding="utf-8")
    assert '<a class="btn" href="../../calendar/">December →'.replace("December →", "") in jan and "← December" in jan
    today_cell = cal.split('data-date="2098-12-31"')[1].split('class="cal-day"')[0]
    assert "Tonight gig" in today_cell and "Already over" in today_cell and "Rejected gig" not in today_cell   # the day shows its whole day; rejected never
    assert 'data-date="2099-01-02"' in jan and "Weekly bingo" in jan and "Too far out" in jan   # every date of a series, 8 days out included
    assert "Waiting for review" not in jan and 'id="category"' in cal
    for a in ("tokens.css", "site.css", "site.js", "review.js"):
        assert (out / "assets" / a).exists()
    assert "—" not in html   # no em dashes in public copy
    # The call to action opens the pop-up form, which is the same form as /add/.
    assert 'data-dialog="add-dialog"' in html and '<dialog class="add-dialog" id="add-dialog"' in html
    add = (out / "add" / "index.html").read_text(encoding="utf-8")
    assert 'class="add-form"' in add and 'name="website"' in add and "robots" not in add
    for t in config.TOWNS:
        assert f'<option value="{t}">{t}</option>' in add
    assert 'data-action=""' in add and 'action="mailto:hello@slack-tide.org"' in add   # no Google Form configured yet
    # The review queue: noindex, one card per pending series, the saved decision metadata on each.
    review = (out / "review" / "index.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex' in review and 'data-repo="cmandle/Slack-Tide"' in review
    assert review.count('class="rev"') == 1 and 'data-id="waiting-for-review"' in review and 'data-decide="approved"' in review
    assert "Rejected gig" not in review and "Tonight gig" not in review
    assert "review.js" in review and "—" not in review

def test_card_art_by_family_and_stable_hash(data, tmp_path, monkeypatch):
    art = tmp_path / "design" / "art"
    art.mkdir(parents=True)
    for name in ("music-1", "music-2", "music-3", "outdoors-1", "general-1", "general-2"):
        (art / f"{name}.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 9 6"/>', encoding="utf-8")
    monkeypatch.setattr(build, "DESIGN", tmp_path / "design")
    monkeypatch.setattr(build, "ART", art)
    scenes = build.art_scenes()
    assert set(scenes) == {"music", "outdoors", "general"} and len(scenes["music"]) == 3
    gig = {"id": "tonight-gig", "category": "Music"}
    assert build.art_for(gig, scenes).startswith("music-")
    assert build.art_for(gig, scenes) == build.art_for(dict(gig), scenes)          # stable across builds
    assert build.art_for({"id": "x", "category": "Sports & Recreation"}, scenes) == "outdoors-1.svg"   # by family
    assert build.art_for({"id": "x", "category": ""}, scenes).startswith("general-")                     # unclassified
    assert build.art_for({"id": "x", "category": "Library & Talks"}, scenes).startswith("general-")     # family with no scenes yet
    picks = {build.art_for({"id": f"series-{i}", "category": "Music"}, scenes) for i in range(40)}
    assert picks == {"music-1.svg", "music-2.svg", "music-3.svg"}                 # the hash spreads neighbours
    out = tmp_path / "site"
    r = build.build(data, out, now=NOW)
    assert r["art"] == 6 and (out / "assets" / "art" / "music-2.svg").exists()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="card-art ill"' in html and 'src="assets/art/music-' in html and 'class="card-art ht"' not in html

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
