"""Fill in coordinates in venues.yaml, and list the venue strings it does not cover.

    python pipeline/tools/geocode_venues.py            # geocode every entry without lat and lon
    python pipeline/tools/geocode_venues.py --missing  # venue strings in data/events.json that match no entry
    python pipeline/tools/geocode_venues.py --check    # entries still without coordinates

Two free, keyless services, in this order: the US Census Bureau geocoder for entries with a
street address (exact for MA and RI street numbers), then OpenStreetMap's Nominatim by name and
town for places without one (nature reserves, farms, parks). Nominatim asks for one request a
second and an identifying User-Agent; both are honoured here. The result is written into the
file as text, under the entry's `town:` line, so the comments survive; the entry gets a
`geocoded:` line naming the service and the date. Nothing already filled is touched: fix a
wrong pin by editing lat and lon by hand and setting `geocoded: hand <date>`.

The pipeline never calls this. Run it after adding entries, commit the file.
"""
from __future__ import annotations
import argparse, json, re, sys, time
from collections import Counter
from datetime import date
from pathlib import Path
import requests, yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from slacktide.normalize import venue_key, venue_aliases   # noqa: E402

VENUES = ROOT / "venues.yaml"
EVENTS = ROOT / "data" / "events.json"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "slack-tide-geocoder/0.1 (https://www.slack-tide.org; hello@slack-tide.org)"
STATE = {"Tiverton": "RI", "Little Compton": "RI"}


def census(address: str) -> tuple[float, float] | None:
    r = requests.get(CENSUS, params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    matches = (r.json().get("result") or {}).get("addressMatches") or []
    if not matches:
        return None
    c = matches[0]["coordinates"]
    return round(float(c["y"]), 5), round(float(c["x"]), 5)


def nominatim(name: str, town: str) -> tuple[float, float] | None:
    q = f"{name}, {town}, {STATE.get(town, 'MA')}"
    r = requests.get(NOMINATIM, params={"q": q, "format": "jsonv2", "limit": 1},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    rows = r.json() or []
    time.sleep(1.1)   # Nominatim's usage policy: one request a second
    if not rows:
        return None
    return round(float(rows[0]["lat"]), 5), round(float(rows[0]["lon"]), 5)


def insert_coords(text: str, vid: str, lat: float, lon: float, how: str) -> str:
    """Put lat, lon and geocoded lines under the entry's `town:` line, by text, so comments stay."""
    m = re.search(rf"^- id: {re.escape(vid)}\s*$", text, re.M)
    if not m:
        raise ValueError(f"entry {vid} not found")
    nxt = re.search(r"^- id: ", text[m.end():], re.M)
    block_end = m.end() + (nxt.start() if nxt else len(text) - m.end())
    block = text[m.end():block_end]
    tm = re.search(r"^  town: .*$", block, re.M)
    if not tm:
        raise ValueError(f"entry {vid} has no town line")
    lines = f"\n  lat: {lat}\n  lon: {lon}\n  geocoded: {how} {date.today().isoformat()}"
    at = m.end() + tm.end()
    return text[:at] + lines + text[at:]


def geocode(dry: bool = False) -> int:
    text = VENUES.read_text(encoding="utf-8")
    venues = yaml.safe_load(text) or []
    done = 0
    for v in venues:
        if v.get("lat") is not None and v.get("lon") is not None:
            continue
        hit, how = None, ""
        if v.get("address"):
            try:
                hit = census(v["address"]); how = "census"
            except Exception as e:
                print(f"{v['id']}: census failed ({type(e).__name__}: {e})")
        if hit is None:
            try:
                hit = nominatim(v.get("query") or v["name"], v["town"]); how = "nominatim"
            except Exception as e:
                print(f"{v['id']}: nominatim failed ({type(e).__name__}: {e})")
        if hit is None:
            print(f"{v['id']}: no result; stays at the {v['town']} town centre")
            continue
        print(f"{v['id']}: {hit[0]}, {hit[1]} ({how})")
        if not dry:
            text = insert_coords(text, v["id"], hit[0], hit[1], how)
        done += 1
    if not dry and done:
        VENUES.write_text(text, encoding="utf-8")
    print(f"{done} entr{'y' if done == 1 else 'ies'} geocoded" + (" (dry run, nothing written)" if dry else ""))
    return 0


def missing() -> int:
    """Venue strings in the last run that match no entry: by count, the to-do list for this file."""
    if not EVENTS.exists():
        print("no data/events.json; run the pipeline first"); return 1
    aliases = venue_aliases(yaml.safe_load(VENUES.read_text(encoding="utf-8")) or [])
    counts: Counter = Counter()
    for s in json.loads(EVENTS.read_text(encoding="utf-8"))["series"]:
        raw = s.get("venue") or ""
        if raw and venue_key(raw) not in aliases:
            counts[(raw, s.get("town") or "")] += 1
    for (raw, town), n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{n:3d}  {raw}  [{town or 'no town'}]")
    print(f"{len(counts)} venue string{'' if len(counts) == 1 else 's'} without an entry")
    return 0


def check() -> int:
    venues = yaml.safe_load(VENUES.read_text(encoding="utf-8")) or []
    bare = [v for v in venues if v.get("lat") is None or v.get("lon") is None]
    for v in bare:
        print(f"{v['id']}  [{v['town']}]  {v.get('note') or ''}")
    print(f"{len(bare)} of {len(venues)} entries without coordinates")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--missing", action="store_true", help="list venue strings in data/events.json with no entry")
    ap.add_argument("--check", action="store_true", help="list entries without coordinates")
    ap.add_argument("--dry-run", action="store_true", help="look up but do not write")
    a = ap.parse_args(argv)
    if a.missing:
        return missing()
    if a.check:
        return check()
    return geocode(dry=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
