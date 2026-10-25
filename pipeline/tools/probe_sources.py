"""Probe candidate source sites for feeds and platform fingerprints.

    python pipeline/tools/probe_sources.py docs/sources-candidates.csv > probe.md

Reads a CSV of town,name,domain,kind and prints a Markdown table: HTTP status of the home
page, the platform fingerprints found in it, which of our known feed shapes answered
(WordPress Events Calendar REST, its iCal twin, the CivicPlus iCal path, Squarespace RSS,
plain RSS), and the event-ish links on the home page. It is how docs/SOURCES.md was compiled
on 2026-10-25; rerun it when the list changes or a site is redesigned. Read-only, polite
(one request per probe, browser user agent, 20 s timeout), ten sites at a time.
"""
from __future__ import annotations
import csv, json, re, sys, concurrent.futures as cf
from pathlib import Path
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
TIMEOUT = 20

FINGERPRINTS = [
    ("wordpress", r"wp-content|wp-json"),
    ("tribe-plugin", r"tribe-events|the-events-calendar"),
    ("squarespace", r"squarespace"),
    ("wix", r"wixstatic|wix\.com|_wix"),
    ("webflow", r"webflow"),
    ("craft", r"SEOmatic|craftcms"),
    ("drupal", r"Drupal"),
    ("joomla", r"Joomla"),
    ("bentobox", r"bentobox"),
    ("civicplus", r"civicplus|/common/modules/|CivicEngage"),
    ("whofi", r"whofi"),
    ("libcal", r"libcal|springshare"),
    ("localist", r"localist"),
    ("google-calendar", r"calendar\.google\.com/calendar"),
    ("eventbrite", r"eventbrite\.com"),
    ("fareharbor", r"fareharbor"),
    ("showare", r"showare"),
    ("salesforce-tickets", r"salesforce-sites\.com/ticket"),
    ("neoncrm", r"neoncrm"),
    ("growthzone", r"growthzone|chambermaster"),
    ("event-espresso", r"event-espresso"),
    ("eventprime", r"eventprime"),
    ("eventon", r"EventON"),
    ("mailchimp", r"list-manage\.com|mailchimp"),
    ("ics-link", r"\.ics\b|ical=1|webcal:"),
    ("json-ld-event", r'"@type"\s*:\s*"Event"'),
]


def get(url: str) -> tuple[int | None, str]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.text[:400000]
    except Exception as e:
        return None, type(e).__name__


def probe(row: dict) -> dict:
    dom = row["domain"].strip()
    out = {"town": row["town"], "name": row["name"], "domain": dom, "kind": row.get("kind", "")}
    base = f"https://{dom}"
    code, body = get(base + "/")
    out["home"] = code if code is not None else body
    if code is None:
        out.update(fingerprints=[], generator="", event_links=[], feeds={})
        return out
    out["fingerprints"] = [name for name, pat in FINGERPRINTS if re.search(pat, body, re.I)]
    gen = re.search(r'<meta name="generator" content="([^"]+)"', body, re.I)
    out["generator"] = gen.group(1)[:50] if gen else ""
    out["event_links"] = sorted(set(re.findall(
        r'href="((?:https?://[^"]*|/[^"]*)(?:event|calendar|whats-on|happening|program)[^"]*)"', body, re.I)))[:4]
    feeds: dict = {}
    c, b = get(base + "/wp-json/tribe/events/v1/events?per_page=1")
    if c == 200 and "{" in b and '"events"' in b:
        try:
            feeds["tribe"] = json.loads(b[b.find("{"):]).get("total")
        except ValueError:
            feeds["tribe"] = "json?"
    c, b = get(base + "/events/?ical=1")
    if c == 200 and b.lstrip().startswith("BEGIN:VCALENDAR"):
        feeds["tribe-ical"] = b.count("BEGIN:VEVENT")
    c, b = get(base + "/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar")
    if c == 200 and "BEGIN:VCALENDAR" in b[:200]:
        feeds["civicplus-ical-cat14"] = b.count("BEGIN:VEVENT")
    if "squarespace" in out["fingerprints"]:
        for path in ("/events", "/calendar"):
            c, b = get(f"{base}{path}?format=json")
            if c == 200 and b.lstrip().startswith("{"):
                try:
                    items = json.loads(b).get("items") or []
                except ValueError:
                    items = []
                dated = [i for i in items if i.get("startDate")]
                if dated:
                    feeds[f"squarespace-json {path}"] = len(dated)
    c, b = get(base + "/feed/")
    if c == 200 and ("<rss" in b[:400] or "<feed" in b[:400]):
        feeds["rss"] = b.count("<item>") or b.count("<entry>")
    out["feeds"] = feeds
    return out


def main(path: str) -> None:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(probe, rows))
    print("| Town | Organisation | Domain | Home | Platform | Feeds | Event links |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        plat = " ".join(x for x in (r["generator"], ",".join(r["fingerprints"])) if x)
        print(f"| {r['town']} | {r['name']} | {r['domain']} | {r['home']} | {plat} | "
              f"{json.dumps(r['feeds'])} | {'; '.join(r['event_links'][:3])} |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2] / "docs" / "sources-candidates.csv"))
