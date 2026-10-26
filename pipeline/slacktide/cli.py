"""Command line: slacktide run | report | tide | build | pending | approve | reject | apply | digest"""
from __future__ import annotations
import argparse, json, sys, time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .config import TZ, load_sources
from .connectors import for_source
from .normalize import normalize
from .series import collapse
from .reconcile import reconcile
from .export import write
from . import approval
from . import tide as tide_mod

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SITE = ROOT / "site"
GATE_SERIES, GATE_TOWNS = 50, 5
REVIEW_URL = "https://www.slack-tide.org/admin/#queue"

def fetch_tide(quiet=False) -> str | None:
    """Best effort: a tide failure never fails the ingest. Returns the error text, if any."""
    try:
        p = tide_mod.write(tide_mod.fetch(), DATA)
        if not quiet:
            print(f"wrote {p}")
        return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"tide: {err} (keeping the previous tide.json, if any)", file=sys.stderr)
        return err

def _ingest(sources, no_cache=False):
    primary, check, errors, timings = [], [], {}, {}
    for s in sources:
        if not s.get("enabled", True):
            continue
        t0 = time.time()
        try:
            occs = for_source(s).fetch() if not no_cache else for_source(s, cache=False).fetch()
        except Exception as e:
            errors[s["id"]] = f"{type(e).__name__}: {e}"
            continue
        timings[s["id"]] = {"rows": len(occs), "seconds": round(time.time() - t0, 2)}
        (check if s.get("role") == "check" else primary).extend(occs)
    towns = {s["id"]: s.get("town", "") for s in sources}
    venues = {s["id"]: s.get("venue", "") for s in sources}
    categories = {s["id"]: s.get("default_category", "") for s in sources}
    normalize(primary, towns, venues, categories)
    normalize(check, towns, venues, categories)
    return primary, check, errors, timings

def weekend_gate(series, now: datetime | None = None) -> dict:
    """Architecture decision 8: fifty distinct series on a typical weekend across at least five
    towns. Measured on the coming Saturday and Sunday, over approved series only: what the gate
    counts is what the public can see."""
    now = now or datetime.now(ZoneInfo(TZ))
    sat = (now + timedelta(days=(5 - now.weekday()) % 7)).date()
    days = {sat.isoformat(), (sat + timedelta(days=1)).isoformat()}
    on = [s for s in series if getattr(s, "approval", "approved") == "approved"
          and any(o["start"][:10] in days for o in s.occurrences)]
    towns = Counter(s.town for s in on)
    return {"saturday": sat.isoformat(), "series": len(on), "towns": dict(towns),
            "passes": len(on) >= GATE_SERIES and len(towns) >= GATE_TOWNS}

def cmd_run(args):
    sources = load_sources()
    primary, check, errors, timings = _ingest(sources, args.no_cache)
    series = collapse(primary)
    decided = approval.apply(series, approval.load(), {s["id"]: s for s in sources})
    dropped = Counter(o.dropped for o in primary if o.dropped)
    gate = weekend_gate(series)
    report = {
        "sources": timings, "errors": errors,
        "primary_rows": len(primary), "dropped": dict(dropped),
        "series": len(series),
        "approval": dict(decided),
        "by_town": dict(Counter(s.town for s in series)),
        "by_category": dict(Counter(s.category or "(unclassified)" for s in series)),
        "by_cadence": dict(Counter(s.cadence for s in series)),
        "weekend_gate": gate,
        "reconcile": reconcile(primary, check) if check else None,
        "tide_error": fetch_tide(quiet=True),
    }
    p = write(series, report, DATA)
    print(f"wrote {p}: {len(series)} series from {len(primary)} rows; dropped {dict(dropped)}; errors {errors}")
    print(f"approval: {decided.get('approved', 0)} approved, {decided.get('pending', 0)} pending, "
          f"{decided.get('rejected', 0)} rejected; queue at data/pending.json")
    print(f"weekend gate ({gate['saturday']}): {gate['series']} series across {len(gate['towns'])} towns, "
          f"{'passes' if gate['passes'] else 'does not pass'} ({GATE_SERIES} series, {GATE_TOWNS} towns)")
    if report["reconcile"]:
        r = report["reconcile"]
        print(f"coverage vs check sources in {', '.join(r['check_towns'])}: {r['check_matched']}/{r['check_total']} rows matched "
              f"({r['coverage_ratio']:.0%}); {r['check_missed_series']} series missed; "
              f"{r['primary_only_series']} primary-only series")
    return 1 if errors and not series else 0

def cmd_report(args):
    rp = DATA / "run-report.json"
    if not rp.exists():
        print("no run-report.json yet; run `slacktide run` first"); return 1
    print(json.dumps(json.loads(rp.read_text(encoding="utf-8")), indent=1))
    return 0

def cmd_tide(args):
    return 1 if fetch_tide() else 0

def cmd_build(args):
    from .build import build
    now = None
    if args.today:
        d = datetime.fromisoformat(args.today)
        now = d.replace(tzinfo=ZoneInfo(TZ)) if d.tzinfo is None else d
    if not (DATA / "events.json").exists():
        print("no data/events.json yet; run `slacktide run` first"); return 1
    r = build(DATA, Path(args.out) if args.out else SITE, now=now)
    print(f"wrote {r['out']}: {r['published']} series published, {r['pending']} waiting for review; "
          f"{r['tonight']} tonight, {r['week']} in the week ahead; tide {r['tide']}; "
          f"tokens from {r['tokens']}; icons from {r['icons']}")
    return 0

# ---------------------------------------------------------------- approval

def _events() -> dict:
    p = DATA / "events.json"
    if not p.exists():
        raise SystemExit("no data/events.json yet; run `slacktide run` first")
    return json.loads(p.read_text(encoding="utf-8"))

def _sources_by_id() -> dict:
    return {s["id"]: s for s in load_sources()}

def cmd_pending(args):
    pend = approval.pending_payload(_events()["series"])
    print(f"{pend['pending_count']} waiting, {pend['soon_count']} within {approval.SOON_DAYS} days; "
          f"{pend['approved_count']} approved, {pend['rejected_count']} rejected")
    for r in pend["series"]:
        when = (r.get("next_start") or "")[:16].replace("T", " ")
        where = ", ".join(x for x in (r.get("venue"), r.get("town")) if x)
        flag = "SOON " if r.get("soon") else "     "
        print(f"{flag}{r['id']}  {when:16}  {r['title'][:50]:50}  {where}")
    return 0

def _decide(args, status):
    events = _events()
    by_id = {s["id"]: s for s in events["series"]}
    ids = [i.strip() for i in args.ids if i.strip()]   # ids pasted from a file may carry \r
    if args.all_pending:
        ids += [s["id"] for s in events["series"] if s.get("approval", "pending") == "pending"]
    ids = [i for i in dict.fromkeys(ids)]
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        print(f"not in data/events.json: {', '.join(unknown)}", file=sys.stderr)
    ids = [i for i in ids if i in by_id]
    if not ids:
        print("nothing to decide"); return 1
    n = approval.record(ids, status, args.by, by_id, note=args.note or "")
    counts = approval.reapply(DATA, _sources_by_id())
    print(f"recorded {n} {status}; now {counts.get('approved', 0)} approved, {counts.get('pending', 0)} pending, "
          f"{counts.get('rejected', 0)} rejected. Commit approvals.yaml; the next ingest run publishes.")
    return 0

def cmd_approve(args): return _decide(args, "approved")
def cmd_reject(args): return _decide(args, "rejected")

def cmd_apply(args):
    counts = approval.reapply(DATA, _sources_by_id())
    print(f"applied approvals.yaml: {dict(counts)}")
    return 0

def cmd_digest(args):
    p = DATA / "pending.json"
    pend = json.loads(p.read_text(encoding="utf-8")) if p.exists() else approval.pending_payload(_events()["series"])
    print(approval.digest(pend, args.review_url))
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(prog="slacktide")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch, normalise, collapse, apply approvals, export"); r.add_argument("--no-cache", action="store_true"); r.set_defaults(fn=cmd_run)
    sub.add_parser("reconcile", help="alias for run; reconciliation is part of the report").set_defaults(fn=cmd_run)
    sub.add_parser("report", help="print the last run report").set_defaults(fn=cmd_report)
    sub.add_parser("tide", help="fetch NOAA CO-OPS tide predictions into data/tide.json").set_defaults(fn=cmd_tide)
    b = sub.add_parser("build", help="generate site/ from data/events.json and data/tide.json")
    b.add_argument("--out", help="output folder (default: site/)")
    b.add_argument("--today", help="build as if today were this date or datetime, e.g. 2026-10-18 or 2026-10-18T18:00")
    b.set_defaults(fn=cmd_build)
    sub.add_parser("pending", help="list the series waiting for a decision").set_defaults(fn=cmd_pending)
    for name, fn, help_ in (("approve", cmd_approve, "approve series by id"), ("reject", cmd_reject, "reject series by id")):
        d = sub.add_parser(name, help=help_)
        d.add_argument("ids", nargs="*", help="series ids from `slacktide pending`")
        d.add_argument("--by", required=True, help="who is deciding")
        d.add_argument("--note", help="a line for the record")
        d.add_argument("--all-pending", action="store_true", help="every series currently pending")
        d.set_defaults(fn=fn)
    sub.add_parser("apply", help="re-apply approvals.yaml to data/ without fetching").set_defaults(fn=cmd_apply)
    g = sub.add_parser("digest", help="markdown summary of the review queue, for the Sunday issue")
    g.add_argument("--review-url", default=REVIEW_URL)
    g.set_defaults(fn=cmd_digest)
    args = ap.parse_args(argv)
    sys.exit(args.fn(args))

if __name__ == "__main__":
    main()
