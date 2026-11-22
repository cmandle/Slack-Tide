"""Decision 11: series-level approval from approvals.yaml, source trust, the pending queue,
the record-and-reapply path the CLI uses, and the Sunday digest."""
import json
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from slacktide import approval
from slacktide.models import Series

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)

def series(sid, title, source="zeiterion", days=3, venue="The Zeiterion", town="New Bedford"):
    start = NOW + timedelta(days=days, hours=7)
    return Series(id=sid, title=title, venue=venue, town=town, category="Nightlife", source_id=source,
                  url=f"https://example.org/{sid}", cost="", first_start=start, last_start=start, count=1,
                  cadence="once", weekday=None,
                  occurrences=[{"start": start.isoformat(), "end": None, "all_day": False}], summary="A show.")

SOURCES = {"zeiterion": {"id": "zeiterion", "review": "person"}, "town-tiverton": {"id": "town-tiverton", "review": "auto"}}

def test_load_last_entry_wins_and_ignores_junk(tmp_path):
    p = tmp_path / "approvals.yaml"
    p.write_text("# header\n- id: a\n  status: approved\n  by: luke\n- id: a\n  status: rejected\n  by: luke\n"
                 "- id: b\n  status: maybe\n- not a mapping\n- id: c\n  status: Approved\n", encoding="utf-8")
    d = approval.load(p)
    assert d["a"]["status"] == "rejected" and "b" not in d and d["c"]["status"] == "approved"
    assert approval.load(tmp_path / "missing.yaml") == {}

def test_apply_decisions_trust_and_pending():
    rows = [series("a", "Approved show"), series("b", "New show"), series("c", "Bingo", source="town-tiverton"), series("d", "Rejected show")]
    counts = approval.apply(rows, {"a": {"id": "a", "status": "approved", "by": "luke"}, "d": {"id": "d", "status": "rejected", "by": "luke"}}, SOURCES)
    assert dict(counts) == {"approved": 2, "pending": 1, "rejected": 1}
    assert rows[0].approval == "approved" and rows[0].decided_by == "luke"
    assert rows[1].approval == "pending"
    assert rows[2].approval == "approved" and rows[2].decided_by == "source trust"
    assert rows[3].approval == "rejected"
    assert rows[0].to_dict()["approval"] == "approved"

def test_pending_payload_sorts_soon_first():
    rows = [series("far", "Far off", days=20), series("soon", "This week", days=2), series("mid", "Next week", days=9)]
    approval.apply(rows, {}, SOURCES)
    pend = approval.pending_payload(rows, now=NOW)
    assert pend["pending_count"] == 3 and pend["soon_count"] == 1
    assert [r["id"] for r in pend["series"]] == ["soon", "mid", "far"]
    assert pend["series"][0]["soon"] is True and pend["series"][1]["soon"] is False

def test_record_then_reapply_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "approvals.yaml"
    rows = [series("a", "Show A"), series("b", "Show B")]
    approval.apply(rows, {}, SOURCES)
    data = tmp_path / "data"; data.mkdir()
    (data / "events.json").write_text(json.dumps({"series": [s.to_dict() for s in rows]}), encoding="utf-8")
    by_id = {s.id: s.to_dict() for s in rows}
    assert approval.record(["a"], "approved", "luke", by_id, path=path) == 1
    assert approval.record(["b"], "rejected", "luke", by_id, note="duplicate", path=path) == 1
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Approval decisions") and "title: Show A" in text and "note: duplicate" in text
    counts = approval.reapply(data, SOURCES, decisions=approval.load(path), now=NOW)
    assert dict(counts) == {"approved": 1, "rejected": 1}
    events = json.loads((data / "events.json").read_text(encoding="utf-8"))
    assert {s["id"]: s["approval"] for s in events["series"]} == {"a": "approved", "b": "rejected"}
    assert json.loads((data / "pending.json").read_text(encoding="utf-8"))["pending_count"] == 0
    # A change of mind is a new line; the loader takes the last one.
    approval.record(["b"], "approved", "luke", by_id, path=path)
    assert approval.load(path)["b"]["status"] == "approved"

def test_category_override_survives_reclassification_and_stays_approved(tmp_path):
    """The categories on an entry correct the classifier on every run without a new review; an
    entry without them hands the series back; an old or unknown name never breaks the entry;
    the single `category` key of the first entries still reads as a one-item list."""
    p = tmp_path / "approvals.yaml"
    p.write_text("- id: a\n  status: approved\n  by: luke\n  date: '2026-11-22'\n  edits:\n    categories: [Arts, Learn]\n"
                 "- id: b\n  status: approved\n  by: luke\n  category: Music\n"        # the first taxonomy's name, the old key
                 "- id: c\n  status: approved\n  by: luke\n  category: Downtown\n"     # not ours: dropped, the decision kept
                 "- id: d\n  status: approved\n  by: luke\n  category: Learn\n- id: d\n  status: approved\n  by: coco\n", encoding="utf-8")
    d = approval.load(p)
    assert d["a"]["edits"] == {"categories": ["Arts", "Learn"]} and d["b"]["edits"] == {"categories": ["Nightlife"]}
    assert d["c"]["edits"] == {} and d["c"]["status"] == "approved" and d["d"]["edits"] == {} and "category" not in d["b"]
    rows = [series("a", "Reclassified show"), series("b", "Old name"), series("c", "Bad name"), series("d", "Handed back")]
    for r in rows:
        r.category, r.categories = "Nightlife", ["Nightlife"]      # what the classifier said this run
    approval.apply(rows, d, SOURCES)
    assert [r.category for r in rows] == ["Arts", "Nightlife", "Nightlife", "Nightlife"]      # the primary is the first
    assert rows[0].categories == ["Arts", "Learn"] and rows[1].categories == ["Nightlife"]
    assert rows[0].edited_by == "luke" and rows[0].edited_on == "2026-11-22" and rows[0].original == {"categories": ["Nightlife"]}
    assert rows[1].edited_by == "luke" and rows[2].edited_by == "" and rows[3].edited_by == "" and rows[3].original == {}
    assert all(r.approval == "approved" for r in rows) and rows[0].to_dict()["categories"] == ["Arts", "Learn"]
    # Dicts (events.json rows on reapply) take the override the same way, a single-category row included.
    row = {"id": "a", "source_id": "zeiterion", "category": "Nightlife"}
    approval.apply([row], d, SOURCES)
    assert row["category"] == "Arts" and row["categories"] == ["Arts", "Learn"] and row["edited_by"] == "luke" and row["approval"] == "approved"

def test_edits_override_the_display_record_and_keep_the_series_id():
    """Decision 11 with edits: the id hashes the source's own title and venue (series.py) before
    the edits are laid over the record, so an edited series keeps its id and its approval; the
    pipeline's values are kept in `original`; applying again, or an entry without edits, is clean."""
    from datetime import timedelta
    from slacktide.models import Occurrence
    from slacktide.series import collapse
    start = NOW + timedelta(days=2)
    occ = Occurrence(source_id="zeiterion", source_uid="1", title="Jazz Night - New Bedford", start=start, end=None, all_day=False,
                     venue_raw="The Z", town="New Bedford", url="https://z.org/jazz", description="A night of jazz.", cost="$10",
                     venue="The Zeiterion", category="Nightlife")
    s = collapse([occ])[0]
    sid = s.id
    edits = {"title": "Jazz night", "venue": "The Zeiterion, Penler Space", "town": "Fall River", "description": "Live jazz.",
             "cost": "$12", "url": "https://z.org/jazz-night", "categories": ["Arts", "Nightlife"]}
    decisions = {sid: {"id": sid, "status": "approved", "by": "luke", "date": "2026-11-22", "edits": edits}}
    approval.apply([s], decisions, SOURCES)
    assert s.id == sid and s.approval == "approved"
    assert (s.title, s.venue, s.town, s.summary, s.cost, s.url) == ("Jazz night", "The Zeiterion, Penler Space", "Fall River", "Live jazz.", "$12", "https://z.org/jazz-night")
    assert s.categories == ["Arts", "Nightlife"] and s.category == "Arts"
    assert s.original == {"title": "Jazz Night - New Bedford", "venue": "The Zeiterion", "town": "New Bedford", "description": "A night of jazz.",
                          "cost": "$10", "url": "https://z.org/jazz", "categories": ["Nightlife"]}
    assert s.edits == edits and s.edited_by == "luke" and s.edited_on == "2026-11-22"
    # The same source rows next run collapse to the same id, whatever the approver changed.
    assert collapse([occ])[0].id == sid
    # Applying twice (reapply reads events.json, which already carries the edits) changes nothing.
    d = s.to_dict()
    approval.apply([d], decisions, SOURCES)
    assert d["title"] == "Jazz night" and d["original"]["title"] == "Jazz Night - New Bedford" and d["categories"] == ["Arts", "Nightlife"]
    # A later entry with fewer edits restores the rest from `original`; one with none restores everything.
    approval.apply([d], {sid: {"id": sid, "status": "approved", "by": "coco", "edits": {"cost": "Free"}}}, SOURCES)
    assert d["title"] == "Jazz Night - New Bedford" and d["cost"] == "Free" and d["categories"] == ["Nightlife"] and d["category"] == "Nightlife"
    assert d["original"] == {"cost": "$10"} and d["edited_by"] == "coco"
    approval.apply([d], {sid: {"id": sid, "status": "approved", "by": "coco", "edits": {}}}, SOURCES)
    assert d["cost"] == "$10" and d["original"] == {} and d["edits"] == {} and d["edited_by"] == "" and d["edited_on"] == ""

def test_clean_edits_drops_or_refuses_what_the_pipeline_cannot_apply():
    raw = {"title": " T ", "town": "fall river", "url": "https://x.org", "cost": "", "categories": "Arts, Music, Downtown",
           "venue": "x" * 301, "summary": "not a field"}
    assert approval.clean_edits(raw) == {"title": "T", "town": "Fall River", "url": "https://x.org", "categories": ["Arts", "Nightlife"]}
    assert approval.clean_edits({"town": "Boston", "url": "x.org"}) == {}
    assert approval.clean_edits("nope") == {} and approval.clean_edits(None) == {}
    for bad in ({"summary": "x"}, {"town": "Boston"}, {"url": "x.org"}, {"categories": "Arts, Downtown"}, {"venue": "x" * 301}, "nope"):
        with pytest.raises(ValueError):
            approval.clean_edits(bad, strict=True)

def test_record_with_edits_and_categories_corrects_a_live_series(tmp_path):
    path = tmp_path / "approvals.yaml"
    rows = [series("a", "Show A")]
    by_id = {s.id: s.to_dict() for s in rows}
    approval.record(["a"], "approved", "luke", by_id, path=path)
    # The fix: approve again with the edits; --category takes a comma list, the first one primary.
    approval.record(["a"], "approved", "luke", by_id, path=path, category="Learn, Arts", edits={"title": "Show A, retitled", "cost": "Free"})
    text = path.read_text(encoding="utf-8")
    assert text.count("- id: a") == 2 and "  edits:\n" in text and "    title: Show A, retitled\n" in text and "edits," in text.split("- id:")[0]   # header explains the field
    assert approval.load(path)["a"]["edits"] == {"title": "Show A, retitled", "cost": "Free", "categories": ["Learn", "Arts"]}
    for bad in (dict(category="Jazz"), dict(edits={"summary": "x"}), dict(edits={"town": "Boston"})):
        with pytest.raises(ValueError):
            approval.record(["a"], "approved", "luke", by_id, path=path, **bad)
    assert approval.load(path)["a"]["edits"]["cost"] == "Free"   # nothing was written by the refused calls
    # The CLI's --set pairs become the same record.
    from slacktide.cli import parse_sets
    assert parse_sets(["title=Show A, retitled", "categories=Learn,Arts", "COST= Free "]) == {"title": "Show A, retitled", "categories": "Learn,Arts", "cost": "Free"}
    with pytest.raises(SystemExit):
        parse_sets(["summary=x"])
    with pytest.raises(SystemExit):
        parse_sets(["title"])

def test_admin_page_appended_entries_parse(tmp_path):
    """The Worker appends entries with JSON-quoted scalars and the edits as a block with a flow
    list of categories; they must load as the CLI's do."""
    import yaml
    text = ('- id: "abc"\n  status: approved\n  by: "Luke O\'Brien"\n  date: "2026-10-25"\n'
            '  title: "Say \\"hi\\": a show"\n  venue: "The Z"\n'
            '  edits:\n    title: "Say \\"hello\\""\n    description: "Two\\nlines"\n    categories: ["Arts", "Learn"]\n')
    entries = yaml.safe_load(text)
    assert entries[0]["title"] == 'Say "hi": a show' and entries[0]["by"] == "Luke O'Brien"
    p = tmp_path / "approvals.yaml"
    p.write_text(text, encoding="utf-8")
    assert approval.load(p)["abc"]["edits"] == {"title": 'Say "hello"', "description": "Two\nlines", "categories": ["Arts", "Learn"]}

def test_digest_markdown():
    rows = [series("soon", "This week", days=2), series("far", "Far off", days=20, town="Fall River")]
    approval.apply(rows, {}, SOURCES)
    md = approval.digest(approval.pending_payload(rows, now=NOW), "https://example.org/review/")
    assert md.startswith("**2 series waiting**, 1 of them starting within 7 days.")
    assert "## Starting within 7 days" in md and "## Fall River" in md and "`far`" in md
    assert "Nothing is waiting" in approval.digest({"series": [], "pending_count": 0, "soon_count": 0}, "x")
