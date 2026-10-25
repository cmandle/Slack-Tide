"""The approval step: a person decides what publishes (decision 11).

Decisions live in ``approvals.yaml`` at the repository root, one entry per series id, appended
by the review page (through the GitHub contents API) or by ``slacktide approve`` and
``slacktide reject``. The file is append-only in spirit: the last entry for an id wins, so a
change of mind is a new line, not an edit, and the history stays readable.

The unit is the series. Its id is a hash of source, title key and venue, so a decision outlives
new dates, but a retitled or moved series is a new id and comes back to the queue. Sources with
``review: auto`` in sources.yaml publish without a decision; none has earned that yet.
"""
from __future__ import annotations
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
APPROVALS = ROOT / "approvals.yaml"
STATUSES = ("approved", "rejected")
SOON_DAYS = 7

HEADER = """# Approval decisions. One entry per series id; the last entry for an id wins.
# Written by the review page (/review/) and by `slacktide approve` / `slacktide reject`.
# Append, never rewrite history: a change of mind is a new entry below the old one.
# title and venue are for the reader; matching is by id alone.
"""


def load(path: Path = APPROVALS) -> dict[str, dict]:
    """Decisions by series id. A missing or empty file is an empty queue of decisions."""
    if not path.exists():
        return {}
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(entries, list):
        raise ValueError(f"{path} must be a list of entries")
    out: dict[str, dict] = {}
    for e in entries:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        status = str(e.get("status", "")).lower()
        if status not in STATUSES:
            continue
        out[str(e["id"])] = {**e, "id": str(e["id"]), "status": status}
    return out


def decide(series_id: str, source_id: str, decisions: dict[str, dict], sources: dict[str, dict]) -> tuple[str, str]:
    """(status, decided_by) for one series: a recorded decision, then source trust, then pending."""
    d = decisions.get(series_id)
    if d:
        return d["status"], str(d.get("by") or "")
    if sources.get(source_id, {}).get("review") == "auto":
        return "approved", "source trust"
    return "pending", ""


def apply(series: list, decisions: dict[str, dict], sources: dict[str, dict]) -> Counter:
    """Set approval and decided_by on Series objects (or series dicts) in place."""
    counts: Counter = Counter()
    for s in series:
        if isinstance(s, dict):
            status, by = decide(s["id"], s["source_id"], decisions, sources)
            s["approval"], s["decided_by"] = status, by
        else:
            status, by = decide(s.id, s.source_id, decisions, sources)
            s.approval, s.decided_by = status, by
        counts[status] += 1
    return counts


def _as_dict(s) -> dict:
    return s if isinstance(s, dict) else s.to_dict()


def pending_payload(series: list, now: datetime | None = None) -> dict:
    """The review queue: pending series, soonest first, with the counts the review page shows.
    `soon` is the number starting within SOON_DAYS; those sit at the top of the queue."""
    now = now or datetime.now(timezone.utc)
    rows = [_as_dict(s) for s in series]
    pending = [r for r in rows if r.get("approval") == "pending"]
    horizon = (now + timedelta(days=SOON_DAYS)).isoformat()

    def next_start(r: dict) -> str:
        for o in r.get("occurrences", []):
            if o["start"] >= now.isoformat():
                return o["start"]
        return r.get("first_start", "")

    for r in pending:
        r["next_start"] = next_start(r)
        r["soon"] = bool(r["next_start"]) and r["next_start"] <= horizon
    pending.sort(key=lambda r: (not r["soon"], r["next_start"] or "9"))
    counts = Counter(r.get("approval") for r in rows)
    return {
        "generated_at": now.isoformat(),
        "pending_count": len(pending),
        "soon_count": sum(1 for r in pending if r["soon"]),
        "approved_count": counts["approved"],
        "rejected_count": counts["rejected"],
        "series": pending,
    }


def record(ids: list[str], status: str, by: str, series_by_id: dict[str, dict] | None = None,
           note: str = "", on: date | None = None, path: Path = APPROVALS) -> int:
    """Append one entry per id. Returns how many were written."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not by:
        raise ValueError("a decision needs a name (--by)")
    series_by_id = series_by_id or {}
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    entries = existing if isinstance(existing, list) else []
    today = (on or date.today()).isoformat()
    for sid in ids:
        s = series_by_id.get(sid, {})
        entry = {"id": sid, "status": status, "by": by, "date": today}   # not "on": YAML reads that key as a boolean
        if s.get("title"):
            entry["title"] = s["title"]
        if s.get("venue"):
            entry["venue"] = s["venue"]
        if note:
            entry["note"] = note
        entries.append(entry)
    body = yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)
    path.write_text(HEADER + body, encoding="utf-8")
    return len(ids)


def reapply(data_dir: Path, sources: dict[str, dict], decisions: dict[str, dict] | None = None,
            now: datetime | None = None) -> Counter:
    """Re-read data/events.json, apply the current decisions and rewrite events.json and
    pending.json without fetching anything. What `slacktide approve` runs after recording."""
    p = data_dir / "events.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    decisions = load() if decisions is None else decisions
    counts = apply(payload["series"], decisions, sources)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (data_dir / "pending.json").write_text(
        json.dumps(pending_payload(payload["series"], now), ensure_ascii=False, indent=1), encoding="utf-8")
    return counts


def digest(pending: dict, review_url: str) -> str:
    """Markdown for the Sunday review issue: counts, the soon list, then the rest by town."""
    rows = pending.get("series", [])
    lines = [f"**{pending.get('pending_count', len(rows))} series waiting**, "
             f"{pending.get('soon_count', 0)} of them starting within {SOON_DAYS} days. "
             f"Review and decide at {review_url}", ""]
    if not rows:
        lines.append("Nothing is waiting. Enjoy the evening.")
        return "\n".join(lines)

    def line(r: dict) -> str:
        when = (r.get("next_start") or r.get("first_start") or "")[:16].replace("T", " ")
        where = ", ".join(x for x in (r.get("venue"), r.get("town")) if x)
        cad = r.get("cadence", "")
        cad = f" ({cad}, {r.get('count')} dates)" if cad and cad != "once" else ""
        return f"- {when} · **{r.get('title')}** · {where}{cad} · `{r.get('id')}`"

    soon = [r for r in rows if r.get("soon")]
    if soon:
        lines += [f"## Starting within {SOON_DAYS} days", ""] + [line(r) for r in soon] + [""]
    by_town: dict[str, list] = {}
    for r in rows:
        if not r.get("soon"):
            by_town.setdefault(r.get("town") or "Town unknown", []).append(r)
    for town in sorted(by_town):
        lines += [f"## {town}", ""] + [line(r) for r in by_town[town]] + [""]
    return "\n".join(lines)
