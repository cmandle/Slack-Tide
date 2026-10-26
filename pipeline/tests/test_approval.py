"""Decision 11: series-level approval from approvals.yaml, source trust, the pending queue,
the record-and-reapply path the CLI uses, and the Sunday digest."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from slacktide import approval
from slacktide.models import Series

TZ = ZoneInfo("America/New_York")
NOW = datetime(2098, 12, 31, 12, 0, tzinfo=TZ)

def series(sid, title, source="zeiterion", days=3, venue="The Zeiterion", town="New Bedford"):
    start = NOW + timedelta(days=days, hours=7)
    return Series(id=sid, title=title, venue=venue, town=town, category="Music", source_id=source,
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

def test_admin_page_appended_entries_parse():
    """admin.js appends entries with JSON-quoted scalars; they must load as the CLI's do."""
    import yaml
    text = ('- id: "abc"\n  status: approved\n  by: "Luke O\'Brien"\n  date: "2026-10-25"\n'
            '  title: "Say \\"hi\\": a show"\n  venue: "The Z"\n')
    entries = yaml.safe_load(text)
    assert entries[0]["title"] == 'Say "hi": a show' and entries[0]["by"] == "Luke O'Brien"

def test_digest_markdown():
    rows = [series("soon", "This week", days=2), series("far", "Far off", days=20, town="Fall River")]
    approval.apply(rows, {}, SOURCES)
    md = approval.digest(approval.pending_payload(rows, now=NOW), "https://example.org/review/")
    assert md.startswith("**2 series waiting**, 1 of them starting within 7 days.")
    assert "## Starting within 7 days" in md and "## Fall River" in md and "`far`" in md
    assert "Nothing is waiting" in approval.digest({"series": [], "pending_count": 0, "soon_count": 0}, "x")
