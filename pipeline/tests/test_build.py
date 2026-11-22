"""The site generator: selection rules, configuration-driven lists, the tide panel's three states
and the pages. Runs offline against a small events.json written by the test."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
from conftest import fixture_text
from slacktide import config, build, tide

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)   # a Wednesday

def series(title, starts, town="Fall River", category="Nightlife", cadence="once", source="viva-fall-river", all_day=False, sid=None, approval="approved"):
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
               town="Tiverton", category="Community", cadence="weekly", source="town-tiverton"),
        series("Next weekend fair", [today + timedelta(days=4)], town="Dartmouth", category="Seasonal", all_day=True, source="dnrt"),
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
    for cat in config.CATEGORIES:                 # one tile per category, from configuration, in its order
        assert f'class="tile" type="button" data-cat="{cat.lower()}"' in html
    assert [t.split('"')[0] for t in html.split('class="tile" type="button" data-cat="')[2:]] == [c.lower() for c in config.CATEGORIES]
    assert set(config.CATEGORY_FAMILY_OF) == set(config.CATEGORIES)   # every taxonomy entry has a slug
    assert 'data-cat="community" data-category="Community"' in html   # bingo is Community
    assert html.count('class="card"') == 1 and html.count('class="week-card"') == 3 and 'class="week-grid"' in html
    assert 'id="category"' not in html and 'id="section"' not in html   # removed 2026-11-08; tiles and tabs replace them
    assert '<a class="tab" href="groups/">' in html and "Volunteer opportunities" not in html
    assert 'data-source="viva-fall-river"' in html and 'class="card-prov" title="Viva Fall River">Read by a person' in html
    assert "Tide data unavailable" in html and 'data-state="unavailable"' in html
    assert "Too far out" not in html and "Already over" not in html
    assert "Waiting for review" not in html and "Rejected gig" not in html   # decision 11: only approved series publish
    assert r["published"] == 6 and r["pending"] == 1
    # The week card: date cell, time, place, town chip and the category band, in start order.
    assert '<span class="wk-day">FRI JAN 2</span><span class="wk-time">6:00 PM</span>' in html   # NOW is Dec 31, the week is January
    assert '<span class="wk-chip">Tiverton</span>' in html and '<span class="wk-band" title="Community">Community</span>' in html
    assert '<span class="wk-time">All day</span>' in html
    assert '<span class="wk-day">SUN JAN 4</span>' in html   # the month joins the day across the month boundary
    order = [m for m in ("Unclassified talk", "Weekly bingo", "Next weekend fair") if m in html]
    assert [html.index(t) for t in order] == sorted(html.index(t) for t in order)
    assert "Archivo" in html and 'href="calendar/"' in html and 'href="map/"' in html
    assert 'id="week-empty" hidden' in html and 'id="tonight-empty" hidden' in html   # both lists have rows
    assert "<h1>Today</h1>" in html and '<span class="card-badge">Today</span>' in html   # same-day at any hour, relabelled 2026-11-22
    assert 'aria-label="Today"' in html and "Nothing listed for today" in html and 'aria-label="Tonight"' not in html
    p = out / "map" / "index.html"
    assert p.exists() and "is coming" not in p.read_text(encoding="utf-8")   # the Map view; test_map.py covers it
    assert not (out / "volunteer").exists() and "volunteer/" not in html   # section retired 2026-11-08
    assert 'id="category"' not in html and 'id="section"' not in html     # the tiles and tabs replace both selects
    assert (out / "groups" / "index.html").exists()   # the directory; test_groups.py covers it
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
    assert "Waiting for review" not in jan and 'class="tile"' in cal and 'href="../calendar/" aria-current="page"' in cal and 'aria-current="page">' + '' not in html.split('class="links"')[1].split('</nav>')[0] and 'id="category"' not in cal
    for a in ("tokens.css", "site.css", "site.js", "admin.js"):
        assert (out / "assets" / a).exists()
    assert not (out / "assets" / "review.js").exists()
    assert "—" not in html   # no em dashes in public copy
    # The call to action opens the pop-up form, which is the same form as /add/.
    assert 'data-dialog="add-dialog"' in html and '<dialog class="add-dialog" id="add-dialog"' in html
    add = (out / "add" / "index.html").read_text(encoding="utf-8")
    assert 'class="add-form"' in add and 'name="website"' in add and "robots" not in add
    for t in config.TOWNS:
        assert f'<option value="{t}">{t}</option>' in add
    assert 'data-action=""' in add and 'action="mailto:hello@slack-tide.org"' in add   # no Google Form configured yet
    # The admin page: noindex, four tabs, one queue card per pending series with the decision
    # metadata on it, the registry table, the tracker rows, the approvers; /review/ redirects there.
    admin = (out / "admin" / "index.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex' in admin and 'data-repo="cmandle/Slack-Tide"' in admin
    for tab in ("#queue", "#sources", "#runs", "#people"):
        assert f'href="{tab}"' in admin
    assert admin.count('class="rev"') == 1 and 'data-id="waiting-for-review"' in admin and 'data-decide="approved"' in admin
    assert 'data-source="zeiterion"' in admin and "Rejected gig" not in admin
    # The category select on the queue item carries the classifier's call and the seven to pick from;
    # the Published list under the queue is where a live series' category is corrected.
    rev = admin.split('class="rev"')[1].split("</article>")[0]
    assert 'data-category-select data-original="Nightlife"' in rev and '<option value="Nightlife" selected>Nightlife</option>' in rev
    assert rev.count("<option") == 1 + len(config.CATEGORIES) and "Arts &amp; Theatre" not in admin
    assert 'id="pub-list"' in admin and admin.count('class="pub"') == 6 and "Published series · 6 live" in admin
    pub = admin.split('data-id="tonight-gig"')[1].split("</div></div>")[0]
    assert 'data-original="Nightlife"' in pub and "Viva Fall River" in pub
    assert "Waiting for review" not in admin.split('id="pub-list"')[1] and "Rejected gig" not in admin
    assert 'id="trk"' in admin and 'id="ppl"' in admin and "admin.js" in admin and "—" not in admin
    assert 'data-approvals="approvals.yaml"' in admin and 'data-tracker="docs/sources-tracker.csv"' in admin
    review = (out / "review" / "index.html").read_text(encoding="utf-8")
    assert 'url=../admin/#queue' in review and "noindex" in review

def test_card_art_by_family_and_stable_hash(data, tmp_path, monkeypatch):
    art = tmp_path / "design" / "art"
    art.mkdir(parents=True)
    for name in ("nightlife-1", "nightlife-2", "nightlife-3", "active-1", "general-1", "general-2"):
        (art / f"{name}.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 9 6"/>', encoding="utf-8")
    monkeypatch.setattr(build, "DESIGN", tmp_path / "design")
    monkeypatch.setattr(build, "ART", art)
    scenes = build.art_scenes()
    assert set(scenes) == {"nightlife", "active", "general"} and len(scenes["nightlife"]) == 3
    gig = {"id": "tonight-gig", "category": "Nightlife"}
    assert build.art_for(gig, scenes).startswith("nightlife-")
    assert build.art_for(gig, scenes) == build.art_for(dict(gig), scenes)          # stable across builds
    assert build.art_for({"id": "x", "category": "Active"}, scenes) == "active-1.svg"       # by category slug
    assert build.art_for({"id": "x", "category": ""}, scenes).startswith("general-")        # unclassified
    assert build.art_for({"id": "x", "category": "Learn"}, scenes).startswith("general-")   # a category with no scenes in this set
    picks = {build.art_for({"id": f"series-{i}", "category": "Nightlife"}, scenes) for i in range(40)}
    assert picks == {"nightlife-1.svg", "nightlife-2.svg", "nightlife-3.svg"}     # the hash spreads neighbours
    out = tmp_path / "site"
    r = build.build(data, out, now=NOW)
    assert r["art"] == 6 and (out / "assets" / "art" / "nightlife-2.svg").exists()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="card-art ill"' in html and 'src="assets/art/nightlife-' in html and 'class="card-art ht"' not in html

def test_repository_art_and_icons_cover_every_category():
    """design/art has three scenes per category plus three general; design/reference/icons and the
    bundled copies have an icon per category plus All."""
    scenes = build.art_scenes()
    assert set(scenes) == {c.lower() for c in config.CATEGORIES} | {"general"}
    assert all(len(v) == 3 for v in scenes.values())
    for base in (build.DESIGN / "reference" / "icons", build.ASSETS / "icons"):
        assert {p.stem for p in base.glob("*.svg")} == {c.lower() for c in config.CATEGORIES} | {"all"}

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
