"""Command line: slacktide run | reconcile | report | tide | build"""
from __future__ import annotations
import argparse, sys, time
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
from . import tide as tide_mod

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SITE = ROOT / "site"
GATE_SERIES, GATE_TOWNS = 50, 5

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
    normalize(primary, towns, venues)
    normalize(check, towns, venues)
    return primary, check, errors, timings

def weekend_gate(series, now: datetime | None = None) -> dict:
    """Architecture decision 8: fifty distinct series on a typical weekend across at least five
    towns. Measured on the coming Saturday and Sunday."""
    now = now or datetime.now(ZoneInfo(TZ))
    sat = (now + timedelta(days=(5 - now.weekday()) % 7)).date()
    days = {sat.isoformat(), (sat + timedelta(days=1)).isoformat()}
    on = [s for s in series if any(o["start"][:10] in days for o in s.occurrences)]
    towns = Counter(s.town for s in on)
    return {"saturday": sat.isoformat(), "series": len(on), "towns": dict(towns),
            "passes": len(on) >= GATE_SERIES and len(towns) >= GATE_TOWNS}

def cmd_run(args):
    sources = load_sources()
    primary, check, errors, timings = _ingest(sources, args.no_cache)
    series = collapse(primary)
    dropped = Counter(o.dropped for o in primary if o.dropped)
    gate = weekend_gate(series)
    report = {
        "sources": timings, "errors": errors,
        "primary_rows": len(primary), "dropped": dict(dropped),
        "series": len(series),
        "by_town": dict(Counter(s.town for s in series)),
        "by_category": dict(Counter(s.category or "(unclassified)" for s in series)),
        "by_cadence": dict(Counter(s.cadence for s in series)),
        "weekend_gate": gate,
        "reconcile": reconcile(primary, check) if check else None,
        "tide_error": fetch_tide(quiet=True),
    }
    p = write(series, report, DATA)
    print(f"wrote {p}: {len(series)} series from {len(primary)} rows; dropped {dict(dropped)}; errors {errors}")
    print(f"weekend gate ({gate['saturday']}): {gate['series']} series across {len(gate['towns'])} towns, "
          f"{'passes' if gate['passes'] else 'does not pass'} ({GATE_SERIES} series, {GATE_TOWNS} towns)")
    if report["reconcile"]:
        r = report["reconcile"]
        print(f"coverage vs check source in {', '.join(r['check_towns'])}: {r['check_matched']}/{r['check_total']} rows matched "
              f"({r['coverage_ratio']:.0%}); {r['check_missed_series']} series missed; "
              f"{r['primary_only_series']} primary-only series")
    return 1 if errors and not series else 0

def cmd_report(args):
    import json
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
    print(f"wrote {r['out']}: {r['tonight']} tonight, {r['week']} in the week ahead; tide {r['tide']}; "
          f"tokens from {r['tokens']}; icons from {r['icons']}")
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(prog="slacktide")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch, normalise, collapse, export"); r.add_argument("--no-cache", action="store_true"); r.set_defaults(fn=cmd_run)
    sub.add_parser("reconcile", help="alias for run; reconciliation is part of the report").set_defaults(fn=cmd_run)
    sub.add_parser("report", help="print the last run report").set_defaults(fn=cmd_report)
    sub.add_parser("tide", help="fetch NOAA CO-OPS tide predictions into data/tide.json").set_defaults(fn=cmd_tide)
    b = sub.add_parser("build", help="generate site/ from data/events.json and data/tide.json")
    b.add_argument("--out", help="output folder (default: site/)")
    b.add_argument("--today", help="build as if today were this date or datetime, e.g. 2026-10-18 or 2026-10-18T18:00")
    b.set_defaults(fn=cmd_build)
    args = ap.parse_args(argv)
    sys.exit(args.fn(args))

if __name__ == "__main__":
    main()
