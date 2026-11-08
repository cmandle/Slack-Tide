"""The Community groups & meetups directory: groups.yaml rendered at /groups/, with a group's
next dates when its events come through the pipeline."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from slacktide import build

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)

GROUPS = [
    {"id": "test-walkers", "name": "Test Walkers", "area": "Westport", "purpose": "Walks on the shore & talks about it.",
     "meets": "Weekly", "join": "Free", "website": "https://example.org/walkers",
     "links": {"instagram": "https://www.instagram.com/walkers/", "luma": "https://luma.com/walkers"},
     "source_id": "walkers-luma", "added": "2098-12-01"},
    {"id": "quiet-group", "name": "Quiet Group", "purpose": "No links yet.", "links": {}},
]


def events_json(tmp_path: Path) -> Path:
    def s(title, start, source, approval="approved"):
        return {"id": title.lower().replace(" ", "-"), "title": title, "venue": "Town Hall", "town": "Westport", "category": "Outdoors & Nature",
                "source_id": source, "url": f"https://example.org/{title}", "cost": "", "first_start": start.isoformat(),
                "last_start": start.isoformat(), "count": 1, "cadence": "once", "weekday": None,
                "occurrences": [{"start": start.isoformat(), "end": None, "all_day": False}], "summary": "", "approval": approval, "decided_by": ""}
    rows = [s("Shore walk", NOW + timedelta(days=3, hours=6), "walkers-luma"),
            s("Dune talk", NOW + timedelta(days=10), "walkers-luma"),
            s("Third thing", NOW + timedelta(days=20), "walkers-luma"),
            s("Not yet approved", NOW + timedelta(days=1), "walkers-luma", approval="pending"),
            s("Someone else", NOW + timedelta(days=2), "other-source")]
    (tmp_path / "events.json").write_text(json.dumps({"generated_at": NOW.isoformat(), "series_count": len(rows),
                                                      "occurrence_count": len(rows), "series": rows}), encoding="utf-8")
    return tmp_path


def test_load_groups_reads_the_repository_file():
    groups = build.load_groups()
    assert [g["id"] for g in groups][:1] == ["south-coast-places-for-people"]
    assert all(g.get("purpose") and g.get("name") for g in groups)
    for g in groups:
        assert "—" not in g["purpose"]            # no em dashes in public copy
        for u in list((g.get("links") or {}).values()) + ([g["website"]] if g.get("website") else []):
            assert u.startswith("https://")


def test_groups_page_is_a_directory_with_next_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "load_groups", lambda root=build.ROOT: GROUPS)
    out = tmp_path / "site"
    build.build(events_json(tmp_path), out, now=NOW)
    html = (out / "groups" / "index.html").read_text(encoding="utf-8")
    assert "is coming" not in html and "<h1>Community groups &amp; meetups</h1>" in html
    assert "2 groups · Swansea to Little Compton" in html
    assert html.count('class="group-card"') == 2 and 'id="test-walkers"' in html
    assert '<h2 class="gc-name">Test Walkers</h2>' in html and "Walks on the shore &amp; talks about it." in html
    assert '<span class="wk-chip">Westport</span>' in html and '<span class="gc-meets">Weekly</span>' in html
    assert '<a class="btn" href="https://example.org/walkers" rel="noopener" target="_blank">Website ↗</a>' in html
    assert 'href="https://luma.com/walkers"' in html and 'href="https://www.instagram.com/walkers/"' in html
    assert html.index("Website ↗") < html.index("Luma ↗") < html.index("Instagram ↗")   # website first, then the fixed order
    # Next dates: the two soonest approved occurrences from the group's source; pending and other sources never.
    assert '<span class="gc-label">Next</span>' in html and "Shore walk" in html and "Dune talk" in html
    assert "Third thing" not in html and "Not yet approved" not in html and "Someone else" not in html
    # A group with nothing but a purpose still renders, without a links row or a Next block.
    quiet = html.split('id="quiet-group"')[1].split("</article>")[0]
    assert "No links yet." in quiet and 'class="gc-links"' not in quiet and "gc-next" not in quiet
    assert 'href="../add/"' in html and 'class="back" href="../"' in html and "—" not in html
    # The section tab for groups is the active one.
    assert 'aria-current="page"' in html.split('class="tabs"')[1].split("</nav>")[0]
