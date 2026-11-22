"""The approval step: a person decides what publishes (decision 11).

Decisions live in ``approvals.yaml`` at the repository root, one entry per series id, appended
by the review page (through the GitHub contents API) or by ``slacktide approve`` and
``slacktide reject``. The file is append-only in spirit: the last entry for an id wins, so a
change of mind is a new line, not an edit, and the history stays readable.

The unit is the series. Its id is a hash of source, title key and venue, so a decision outlives
new dates, but a retitled or moved series is a new id and comes back to the queue. Sources with
``review: auto`` in sources.yaml publish without a decision; a recorded decision still wins, so a
rejected series from such a source stays rejected. The Zeiterion was the first, 2026-11-08.

An entry may also carry ``edits`` (since 2026-11-22): the approver's overrides of what the
pipeline read, keyed as in config.EDITABLE_FIELDS (title, venue, town, description, cost, url,
categories). ``apply`` lays them over the series on every run, after normalisation and
classification, so they survive re-ingest and reclassification; and because the id is computed
from the source's own title and venue before the edits are applied (series.py), an edit never
sends an approved series back through the queue. The same last-entry-wins rule applies to the
edits: a later entry for the id without them hands every field back to the pipeline. The
single ``category`` key of the first day of the seven categories is still read as
``edits: {categories: [category]}``.
"""
from __future__ import annotations
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import yaml
from .config import CATEGORIES, EDITABLE_FIELDS, EDIT_MAX_LENGTH, canonical_categories, canonical_town

ROOT = Path(__file__).resolve().parents[2]
APPROVALS = ROOT / "approvals.yaml"
STATUSES = ("approved", "rejected")
SOON_DAYS = 7

HEADER = """# Approval decisions. One entry per series id; the last entry for an id wins.
# Written by the admin page's Queue tab (/admin/) and by `slacktide approve` / `slacktide reject`.
# Append, never rewrite history: a change of mind is a new entry below the old one.
# title and venue are for the reader; matching is by id alone.
# edits, when present, are the approver's overrides of what the pipeline read (title, venue, town,
# description, cost, url, categories: the first category is the primary) and are laid over the
# series on every run; an entry without them hands every field back to the pipeline and the classifier.
"""


def clean_edits(raw, strict: bool = False) -> dict:
    """The edit record as the pipeline applies it: known keys only, strings stripped, the town one
    of config.TOWNS, the categories canonical and in order, a link starting with http. An empty
    value is no override. With `strict`, anything dropped raises ValueError instead (what the CLI
    wants); otherwise a bad value is dropped and the rest of the entry kept (what load wants)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        if strict:
            raise ValueError("edits must be a mapping of field to value")
        return {}
    out: dict = {}
    for key, value in raw.items():
        if key not in EDITABLE_FIELDS:
            if strict:
                raise ValueError(f"{key!r} is not editable; the fields are {', '.join(EDITABLE_FIELDS)}")
            continue
        if key == "categories":
            cats = canonical_categories(value)
            asked = [v for v in (value.split(",") if isinstance(value, str) else (value or [])) if str(v).strip()]
            if strict and len(cats) != len(dict.fromkeys(asked)):
                raise ValueError(f"categories must be from {', '.join(CATEGORIES)}, got {value!r}")
            if cats:
                out["categories"] = cats
            continue
        s = str(value or "").strip()
        if not s:
            continue
        if len(s) > EDIT_MAX_LENGTH[key]:
            if strict:
                raise ValueError(f"{key} is longer than {EDIT_MAX_LENGTH[key]} characters")
            continue
        if key == "town":
            town = canonical_town(s)
            if not town:
                if strict:
                    raise ValueError(f"town must be one of the fifteen in config.TOWNS, got {s!r}")
                continue
            s = town
        if key == "url" and not s.lower().startswith(("http://", "https://")):
            if strict:
                raise ValueError("url must start with http:// or https://")
            continue
        out[key] = s
    return out


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
        entry = {**e, "id": str(e["id"]), "status": status}
        # The edits as the pipeline will apply them. A value that names nothing we know (a
        # category under an old name still lands on one of the seven) is dropped from the record,
        # not the entry from the file. The single `category` key of the first entries is read as
        # a one-item category list unless the entry's edits name their own.
        edits = clean_edits(entry.pop("edits", None))
        legacy = entry.pop("category", None)
        if legacy and "categories" not in edits:
            edits.update(clean_edits({"categories": legacy}))
        entry["edits"] = edits
        out[entry["id"]] = entry
    return out


def decide(series_id: str, source_id: str, decisions: dict[str, dict], sources: dict[str, dict]) -> tuple[str, str]:
    """(status, decided_by) for one series: a recorded decision, then source trust, then pending."""
    d = decisions.get(series_id)
    if d:
        return d["status"], str(d.get("by") or "")
    if sources.get(source_id, {}).get("review") == "auto":
        return "approved", "source trust"
    return "pending", ""


def edits_for(series_id: str, decisions: dict[str, dict]) -> tuple[dict, str, str]:
    """(edits, by, date) from the last entry for the id; ({}, "", "") when it carries none."""
    d = decisions.get(series_id) or {}
    edits = d.get("edits") or {}
    if not edits:
        return {}, "", ""
    return edits, str(d.get("by") or ""), str(d.get("date") or "")


def apply_edits(d: dict, edits: dict, by: str = "", on: str = "") -> None:
    """Lay the approver's edits over one series record (a dict, or vars() of a Series) in place.

    The pipeline's own value of every overridden field is kept in `original`, so the record can
    be re-read and re-applied any number of times (reapply runs on data/events.json, which already
    carries the last application) and a later entry without an edit restores the field. The
    category list is the classifier's single category unless the edits set one; `category` is
    always its first entry, for everything that still reads one."""
    orig = dict(d.get("original") or {})
    for key, fld in EDITABLE_FIELDS.items():
        if key == "categories":
            base = orig["categories"] if "categories" in orig else list(d.get("categories") or ([d["category"]] if d.get("category") else []))
        else:
            base = orig[key] if key in orig else d.get(fld, "")
        if key in edits:
            orig[key] = base
            d[fld] = list(edits[key]) if key == "categories" else edits[key]
        else:
            orig.pop(key, None)
            d[fld] = base
    d["category"] = d["categories"][0] if d["categories"] else ""
    d["original"] = orig
    d["edits"] = dict(edits)
    d["edited_by"] = by if edits else ""
    d["edited_on"] = on if edits else ""


def apply(series: list, decisions: dict[str, dict], sources: dict[str, dict]) -> Counter:
    """Set approval and decided_by, and lay the entry's edits over the record, on Series objects
    (or series dicts) in place. Runs on every ingest and on reapply, so an edit or a corrected
    category outlives the pipeline's next reading."""
    counts: Counter = Counter()
    for s in series:
        d = s if isinstance(s, dict) else vars(s)
        status, by = decide(d["id"], d["source_id"], decisions, sources)
        d["approval"], d["decided_by"] = status, by
        apply_edits(d, *edits_for(d["id"], decisions))
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
           note: str = "", on: date | None = None, path: Path = APPROVALS, category: str = "",
           edits: dict | None = None) -> int:
    """Append one entry per id. Returns how many were written. `edits` (config.EDITABLE_FIELDS)
    and `category` (one name, or several with commas, the first primary) are laid over every id
    in the call on every run; approving an already approved series with them is the way to edit
    a live listing. A bad field or value raises ValueError before anything is written."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not by:
        raise ValueError("a decision needs a name (--by)")
    edits = dict(edits or {})
    if category:
        edits["categories"] = category
    edits = clean_edits(edits, strict=True)
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
        if edits:
            entry["edits"] = edits
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
