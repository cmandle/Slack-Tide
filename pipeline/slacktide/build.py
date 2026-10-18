"""Generate the Phase 1 static site, Events section, from data/events.json and data/tide.json.

``slacktide build`` writes ``site/index.html``, the placeholder pages and ``site/assets/``.
Plain HTML, CSS and JavaScript; no framework (architecture decision 2). The look is
design/DESIGN.md (Revision B of the Claude Design canvas): the stylesheet is design/tokens.css
as the variable layer plus the component layer in ``site_assets/site.css``. When
``design/tokens.css`` or ``design/reference/icons/*.svg`` are missing the bundled copies in
``site_assets/`` stand in.

Towns and the category taxonomy come from ``config``; the template never lists them.
Tonight shows series whose next occurrence is today. The week ahead lists the following seven
days with each collapsed series as one row, on the day of its next occurrence.
"""
from __future__ import annotations
import hashlib, html, json, os, re, shutil
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from . import config, tide as tide_mod

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).with_name("site_assets")
# SLACKTIDE_DESIGN points the build at another checkout of design/, for building against a
# design/* branch before it is merged. Default: the design/ folder of this repository.
DESIGN = Path(os.environ.get("SLACKTIDE_DESIGN") or ROOT / "design")
ART = DESIGN / "art"
SITE_NAME = "Slack Tide"
REGION = "Swansea to Little Compton"
WEEK_DAYS = 7
FONT_URL = "https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;900&family=IBM+Plex+Mono:wght@400;500&display=swap"
CONTACT = "mailto:hello@slack-tide.org"

SECTIONS = [  # tabs; the first is this section, the rest are placeholders for now
    ("events", "Events", "Events", ""),
    ("groups", "Community groups & meetups", "Groups & meetups", "groups/"),
    ("volunteer", "Volunteer opportunities", "Volunteer", "volunteer/"),
]
LINKS = [("calendar", "Calendar", "calendar/"), ("map", "Map", "map/"), ("add", "Add your event", "add/")]
STICKER = ("M12 2a3 3 0 013 3l-1 4 4-1a3 3 0 010 6l-4-1 1 4a3 3 0 01-6 0l1-4-4 1a3 3 0 010-6l4 1-1-4a3 3 0 013-3z")

def esc(s) -> str:
    return html.escape(str(s), quote=True)

def slug(s: str) -> str:
    s = s.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def fmt_time(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'PM' if dt.hour >= 12 else 'AM'}"

def fmt_time_short(dt: datetime) -> str:
    """'8A', '10:30A', '7P': the phone artboard's compact form."""
    h = dt.hour % 12 or 12
    m = f":{dt.minute:02d}" if dt.minute else ""
    return f"{h}{m}{'P' if dt.hour >= 12 else 'A'}"

def week_range_label(today: date) -> str:
    """'Oct 19 to 25', or 'Oct 29 to Nov 4' across a month boundary."""
    a, b = today + timedelta(days=1), today + timedelta(days=WEEK_DAYS)
    if a.month == b.month:
        return f"{a.strftime('%b')} {a.day} to {b.day}"
    return f"{a.strftime('%b')} {a.day} to {b.strftime('%b')} {b.day}"

def family_of(cat: str) -> str:
    """The display family slug for a taxonomy category, or "" when unclassified."""
    return config.CATEGORY_FAMILY_OF.get(cat, "")

def stock_var(cat: str) -> str:
    fam = family_of(cat)
    return f"var(--st-cat-{fam})" if fam else "var(--st-rule)"   # unclassified: the light blue rule colour

def short_label(cat: str) -> str:
    fam = family_of(cat)
    return config.CATEGORY_FAMILIES[fam][0] if fam else "Event"

def art_scenes() -> dict[str, list[str]]:
    """The card illustration set, design/art/<family>-<n>.svg, grouped by family. Empty when the
    design package has no art yet."""
    out: dict[str, list[str]] = {}
    if ART.is_dir():
        for p in sorted(ART.glob("*.svg")):
            fam = p.stem.rsplit("-", 1)[0]
            out.setdefault(fam, []).append(p.name)
    return out

def art_for(series: dict, scenes: dict[str, list[str]]) -> str:
    """DESIGN.md, Images: a series without a photo shows a stock scene chosen by family, then by a
    stable hash of the series id across the family's scenes. "general" when unclassified. Returns
    the file name, or "" when the set has nothing to offer."""
    fam = family_of(series.get("category") or "") or "general"
    files = scenes.get(fam) or scenes.get("general") or []
    if not files:
        return ""
    n = int(hashlib.sha1(series["id"].encode()).hexdigest(), 16)
    return files[n % len(files)]

def icon_svg(cat_slug: str) -> str:
    for base in (DESIGN / "reference" / "icons", ASSETS / "icons"):
        p = base / f"{cat_slug}.svg"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    return ""

# ---------------------------------------------------------------- data

def load_events(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s)

def select(series: list[dict], now: datetime) -> tuple[list[dict], dict[date, list[dict]]]:
    """Return (tonight, week) where tonight is a list of {series, start, occ} for today and week
    maps each of the next seven dates to its rows. One row per series in each list."""
    today = now.date()
    horizon = today + timedelta(days=WEEK_DAYS)
    tonight, week = [], {today + timedelta(days=i): [] for i in range(1, WEEK_DAYS + 1)}
    for s in series:
        nxt = None
        for o in s["occurrences"]:
            start = _parse(o["start"])
            end = _parse(o["end"]) if o.get("end") else start + timedelta(hours=2)
            if o.get("all_day"):
                end = max(end, start.replace(hour=23, minute=59))
            if end >= now:
                nxt = (start, o)
                break
        if not nxt:
            continue
        start, o = nxt
        d = start.date()
        row = {"series": s, "start": start, "occ": o}
        if d == today:
            tonight.append(row)
        elif today < d <= horizon:
            week[d].append(row)
    key = lambda r: (not r["occ"].get("all_day"), r["start"], r["series"]["title"])
    tonight.sort(key=key)
    for rows in week.values():
        rows.sort(key=key)
    return tonight, week

def source_index() -> dict[str, dict]:
    return {s["id"]: s for s in config.load_sources()}

def provenance(s: dict, sources: dict[str, dict]) -> str:
    src = sources.get(s["source_id"], {})
    return src.get("provenance") or config.PROVENANCE_DEFAULT

def source_name(s: dict, sources: dict[str, dict]) -> str:
    return sources.get(s["source_id"], {}).get("name") or s["source_id"]

# ---------------------------------------------------------------- tide

def tide_box(tide: dict | None, now: datetime) -> str:
    station = esc(tide["station_name"] if tide else config.TIDE_STATION_NAME)
    top, bottom = 1.0, 83.0
    if not tide or not tide.get("levels"):
        # DESIGN.md: the staff unfilled, the words, no numbers.
        empty_staff = ('<svg class="tide-staff" viewBox="0 0 22 84" role="img" aria-label="Tide staff, no reading">'
                       '<rect class="staff" x="7" y="1" width="8" height="82"/>'
                       '<path class="tick" d="M7 11h4M7 21h6M7 31h4M7 41h6M7 51h4M7 61h6M7 71h4" fill="none"/></svg>')
        return (f'<aside class="tide" id="tide" data-state="unavailable" aria-label="Tide">{empty_staff}'
                f'<div class="tide-readings"><span class="tide-unavailable">Tide data unavailable</span>'
                f'<span class="tide-source">NOAA CO-OPS · {station}</span></div></aside>')
    local_now = now.strftime("%Y-%m-%d %H:%M")
    levels = tide["levels"]
    cur = max((l for l in levels if l["t"] <= local_now), key=lambda l: l["t"], default=levels[0])
    after = [l for l in levels if l["t"] > cur["t"]]
    trend = ""
    if after:
        trend = "rising" if after[0]["v"] > cur["v"] else "falling" if after[0]["v"] < cur["v"] else "slack"
    arrow = {"rising": "↑", "falling": "↓", "slack": "→"}.get(trend, "")
    upcoming = [h for h in tide["hilo"] if h["t"] > local_now][:2]
    vals = [l["v"] for l in levels] + [h["v"] for h in tide["hilo"]]
    lo, hi = min(vals + [0.0]), max(vals)
    smin, smax = float(int(lo) - (1 if lo < 0 else 0)), float(int(hi) + 1)
    # The design's staff: a 22 x 84 viewBox, the column from y=1 to y=83, ticks every foot
    # alternating short and long, water in blue, a coral line at the reading.
    def y_of(v): return bottom - (bottom - top) * (v - smin) / (smax - smin)
    ticks = []
    f = smin
    while f <= smax + 1e-9:
        if smin < f < smax:
            w = 6 if int(round(f)) % 2 == 0 else 4
            ticks.append(f'M7 {y_of(f):.1f}h{w}')
        f += 1.0
    ycur = y_of(cur["v"])
    staff = (f'<svg class="tide-staff" viewBox="0 0 22 84" data-min="{smin}" data-max="{smax}" data-top="{top}" '
             f'data-bottom="{bottom}" role="img" aria-label="Tide staff, {cur["v"]:.1f} feet{" and " + trend if trend else ""}">'
             f'<rect class="staff" x="7" y="1" width="8" height="82"/>'
             f'<rect class="tide-water" x="7.75" y="{ycur:.1f}" width="6.5" height="{bottom - ycur:.1f}"/>'
             f'<path class="tick" d="{" ".join(ticks)}" fill="none"/>'
             f'<g class="tide-mark" transform="translate(0 {ycur:.1f})"><path d="M1 0h20" fill="none"/></g>'
             '</svg>')
    hilo = ('<span class="sep"> · </span>'.join(
        f'<span>{"High" if h["type"] == "H" else "Low"} {esc(fmt_time(datetime.strptime(h["t"], "%Y-%m-%d %H:%M")))}</span>'
        for h in upcoming) or '<span>Next turn after midnight</span>')
    readings = (f'<div class="tide-readings"><span class="tide-now">{cur["v"]:.1f} ft {arrow}'
                f'{"<span class=long> " + trend + "</span>" if trend else ""}</span>'
                f'<span class="tide-hilo">{hilo}</span>'
                f'<span class="tide-source"><span class="short">NOAA · {station}</span>'
                f'<span class="long">NOAA CO-OPS predictions · {station}</span></span></div>')
    data = {"fetched_at": tide["fetched_at"], "max_age_hours": config.TIDE_MAX_AGE_HOURS,
            "utc_offset_minutes": int(now.utcoffset().total_seconds() // 60),
            "levels": levels, "hilo": tide["hilo"]}
    return (f'<aside class="tide" id="tide" data-state="ok" aria-label="Tide">{staff}{readings}'
            '<p class="tide-unavailable" hidden>Tide data unavailable</p>'
            '<script type="application/json" id="tide-data">' + json.dumps(data).replace("</", "<\\/") + '</script>'
            '</aside>')

# ---------------------------------------------------------------- markup

def page(title: str, body: str, rel: str, description: str, generated: datetime) -> str:
    return f"""<!doctype html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="generator" content="slacktide build {esc(generated.isoformat(timespec='minutes'))}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONT_URL}">
<link rel="stylesheet" href="{rel}assets/tokens.css?v={generated.strftime('%Y%m%d%H%M')}">
<link rel="stylesheet" href="{rel}assets/site.css?v={generated.strftime('%Y%m%d%H%M')}">
</head>
<body>
<a class="skip" href="#main">Skip to events</a>
<div class="frame">
{body}
</div>
<script src="{rel}assets/site.js?v={generated.strftime('%Y%m%d%H%M')}" defer></script>
</body>
</html>
"""

def head(active: str, rel: str) -> str:
    tabs = []
    for key, long, short, href in SECTIONS:
        cur = ' aria-current="page"' if key == active else ""
        tabs.append(f'<a class="tab" href="{rel}{href}"{cur}><span class="long">{esc(long)}</span><span class="short">{esc(short)}</span></a>')
    return (f'<header class="head"><div class="brandbar"><a class="wordmark" href="{rel}">slack-tide</a></div>'
            f'<nav class="tabs" aria-label="Sections">{"".join(tabs)}</nav></header>')

def stickers() -> str:
    """Three splats in the empty space after the heading. They are laid out after the h1, so they
    land past the end of whatever the heading says on each page, and site.js nudges them while a
    section tab is hovered or focused."""
    return '<span class="stickers" aria-hidden="true">' + "".join(
        f'<svg class="sticker sticker-{i}" viewBox="0 0 24 24"><path d="{STICKER}" fill="{c}" stroke="#1A1A1A" stroke-width="1.2"/></svg>'
        for i, c in ((1, "var(--st-coral)"), (2, "var(--st-green)"), (3, "var(--st-yellow)"))) + '</span>'

def footer(rel: str) -> str:
    towns = ", ".join(config.TOWNS[:-1]) + " and " + config.TOWNS[-1]
    return (f'<footer class="footer"><div class="lead">Every listing is read by a person before it lands here. '
            f'<span class="towns">{esc(towns)}.</span></div>'
            f'<div>Spotted something wrong? <a href="{CONTACT}">Let us know</a></div></footer>')

def filters(towns_with: Counter, rel: str) -> str:
    opts = ['<option value="">All towns</option>']
    for t in config.TOWNS:
        dis = "" if towns_with.get(t) else " disabled"
        opts.append(f'<option value="{esc(t)}"{dis}>{esc(t)}</option>')
    tiles = [f'<button class="tile" type="button" data-cat="" aria-pressed="true">{icon_svg("all")}<span>All</span></button>']
    for fam, (label, cats) in config.CATEGORY_FAMILIES.items():
        tiles.append(f'<button class="tile" type="button" data-cat="{esc(fam)}" aria-pressed="false" title="{esc(", ".join(cats))}">'
                     f'{icon_svg(fam)}<span>{esc(label)}</span></button>')
    cal = ('<svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><rect x="2" y="4" width="16" height="14" fill="none" stroke="currentColor" stroke-width="2"/>'
           '<path d="M2 8h16M6 2v4M14 2v4" stroke="currentColor" stroke-width="2"/></svg>')
    pin = ('<svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 18s-6-5.5-6-10a6 6 0 0112 0c0 4.5-6 10-6 10z" fill="none" stroke="currentColor" stroke-width="2"/>'
           '<circle cx="10" cy="8" r="2" fill="currentColor"/></svg>')
    return (f'<div class="filters"><div class="select"><label class="visually-hidden" for="town">Town</label>'
            f'<select id="town" name="town">{"".join(opts)}</select>'
            '<svg width="12" height="8" viewBox="0 0 12 8" aria-hidden="true"><path d="M1 1l5 5 5-5" fill="none" stroke="#1A1A1A" stroke-width="2"/></svg></div>'
            f'<nav class="links" aria-label="Views"><a class="btn btn-calendar" href="{rel}calendar/">{cal}Calendar</a>'
            f'<a class="btn" href="{rel}map/">{pin}Map</a></nav>'
            f'<div class="tiles" role="group" aria-label="Categories">{"".join(tiles)}</div></div>')

def card(row: dict, sources: dict, scenes: dict[str, list[str]], rel: str = "") -> str:
    s, start, o = row["series"], row["start"], row["occ"]
    cat = s.get("category") or ""
    when = f'{start.strftime("%a").upper()} {"ALL DAY" if o.get("all_day") else fmt_time(start)}'
    where = ", ".join(x for x in (s.get("venue"), s.get("town")) if x)
    # Photographs take the halftone (.ht); illustrations render as drawn (.ill). No photo field
    # exists in events.json yet, so every card shows a scene from the set.
    photo = s.get("image_url") or ""
    if photo:
        art = f'<div class="card-art ht" aria-hidden="true"><img src="{esc(photo)}" alt="" loading="lazy">'
    else:
        scene = art_for(s, scenes)
        art = (f'<div class="card-art ill" aria-hidden="true"><img src="{rel}assets/art/{esc(scene)}" alt="" loading="lazy">'
               if scene else '<div class="card-art ht" aria-hidden="true">')
    return (f'<a class="card" href="{esc(s["url"] or "#")}" data-town="{esc(s["town"])}" data-cat="{esc(family_of(cat))}" '
            f'data-category="{esc(cat)}" data-source="{esc(s["source_id"])}" data-series="{esc(s["id"])}" style="--cat: {stock_var(cat)}">'
            f'<div class="card-title">{esc(s["title"])}</div>'
            f'<div class="card-media">{art}<span class="card-badge">Tonight</span></div>'
            f'<div class="card-strip" title="{esc(cat)}">{esc(short_label(cat))}</div></div>'
            f'<div class="card-when"><span>{esc(when)}</span><span>{esc(s.get("cost") or "")}</span></div>'
            f'<div class="card-where">{esc(where)}</div>'
            f'<div class="card-prov" title="{esc(source_name(s, sources))}">{esc(provenance(s, sources))}</div></a>')

def week_row(row: dict, sources: dict) -> str:
    s, start, o = row["series"], row["start"], row["occ"]
    cat = s.get("category") or ""
    day = f'{start.strftime("%a").upper()} {start.day}'
    if o.get("all_day"):
        when_short = when_long = f"{day} · All day"
    else:
        when_short, when_long = f"{day} · {fmt_time_short(start)}", f"{day} · {fmt_time(start)}"
    where = ", ".join(x for x in (s.get("venue"), s.get("town")) if x)
    return (f'<a class="week-row" href="{esc(s["url"] or "#")}" data-town="{esc(s["town"])}" data-cat="{esc(family_of(cat))}" '
            f'data-category="{esc(cat)}" data-source="{esc(s["source_id"])}" data-series="{esc(s["id"])}" style="--cat: {stock_var(cat)}" '
            f'title="{esc(provenance(s, sources))} · {esc(source_name(s, sources))}">'
            f'<span class="week-swatch" aria-hidden="true"></span>'
            f'<span class="week-when"><span class="short">{esc(when_short)}</span><span class="long">{esc(when_long)}</span></span>'
            f'<span class="week-main"><span class="week-title">{esc(s["title"])}</span><span class="week-where">{esc(where)}</span></span></a>')

def events_page(events: dict, tide: dict | None, now: datetime) -> str:
    sources = source_index()
    tonight, week = select(events["series"], now)
    towns = Counter(r["series"]["town"] for r in tonight)
    for rows in week.values():
        towns.update(r["series"]["town"] for r in rows)
    n_towns = len([t for t in towns if t])
    dateline = f'{now.strftime("%a")} {now.strftime("%b")} {now.day} · {REGION}'
    scenes = art_scenes()
    cards_html = "".join(card(r, sources, scenes) for r in tonight)
    rows_html = "".join(week_row(r, sources) for rows in week.values() for r in rows)
    n_week = sum(len(r) for r in week.values())
    description = (f"Gigs, markets, walks, talks and town meetings from {REGION}, gathered from the calendars "
                   "local organizations already keep. Every listing is read by a person.")
    body = (head("events", "") +
            '<main class="content" id="main">'
            f'<div class="hero"><div class="hero-text"><div class="hero-title"><h1>Tonight</h1>{stickers()}</div>'
            f'<div class="dateline">{esc(dateline)}<span class="long"> · {n_towns} town{"" if n_towns == 1 else "s"}</span></div></div>'
            + tide_box(tide, now) + '</div>'
            + filters(towns, "") +
            f'<div class="cards" aria-label="Tonight">{cards_html}</div>'
            f'<p class="empty" id="tonight-empty"{"" if not tonight else " hidden"}>Nothing listed for tonight in this view.</p>'
            f'<section class="week" aria-labelledby="week-h"><h2 id="week-h"><span>The week ahead</span><span class="range">{esc(week_range_label(now.date()))}</span></h2>'
            f'{rows_html}'
            f'<p class="empty" id="week-empty"{" hidden" if n_week else ""}>Nothing listed for the week ahead in this view.</p>'
            '<a class="week-more" href="calendar/">See the whole month →</a></section>'
            '<a class="cta" href="add/">Add your event</a>'
            '</main>' + footer(""))
    return page(f"{SITE_NAME} · Events, {REGION}", body, "", description, now)

PLACEHOLDER_COPY = {
    "groups": ("Community groups & meetups", "This section will list the standing groups, clubs and meetups along the coast: who meets, where, and how often."),
    "volunteer": ("Volunteer opportunities", "This section will list the land trusts, libraries, pantries and town committees that need hands, with dates where they have them."),
    "calendar": ("Calendar", "The calendar will expand every series into its dates, a month at a time."),
    "map": ("Map", "The map will place every venue we list, town by town."),
    "add": ("Add your event", "Submissions open in Phase 2. Until then, publish your event on your own calendar and we will read it from there."),
}

def placeholder_page(key: str, now: datetime) -> str:
    rel = "../"
    title, copy = PLACEHOLDER_COPY[key]
    active = key if key in ("groups", "volunteer") else "events"
    body = (head(active, rel) +
            f'<main class="content placeholder" id="main"><div class="hero-text"><div class="hero-title"><h1>{esc(title)}</h1>{stickers()}</div>'
            f'<div class="dateline">Coming soon · {esc(REGION)}</div></div>'
            f'<p>{esc(title)} is coming. {esc(copy)} Until then, the Events page has everything we publish.</p>'
            f'<a class="back" href="{rel}">Back to events →</a></main>' + footer(rel))
    return page(f"{SITE_NAME} · {title}", body, rel, f"{title} is coming to Slack Tide.", now)

# ---------------------------------------------------------------- build

def write_assets(out: Path) -> dict:
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    tokens = DESIGN / "tokens.css"
    used = {"tokens": tokens if tokens.exists() else ASSETS / "tokens.css"}
    shutil.copyfile(used["tokens"], assets / "tokens.css")
    shutil.copyfile(ASSETS / "site.css", assets / "site.css")
    shutil.copyfile(ASSETS / "site.js", assets / "site.js")
    used["icons"] = DESIGN / "reference" / "icons" if (DESIGN / "reference" / "icons").is_dir() else ASSETS / "icons"
    art_out = assets / "art"
    if art_out.is_dir():
        shutil.rmtree(art_out)
    scenes = art_scenes()
    if scenes:
        art_out.mkdir()
        for files in scenes.values():
            for f in files:
                shutil.copyfile(ART / f, art_out / f)
    used["art"] = sum(len(v) for v in scenes.values())
    return used

def build(data_dir: Path, out: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(ZoneInfo(config.TZ))
    events = load_events(data_dir / "events.json")
    tide = tide_mod.load(data_dir / "tide.json", now=now.astimezone(timezone.utc))
    out.mkdir(parents=True, exist_ok=True)
    used = write_assets(out)
    (out / "index.html").write_text(events_page(events, tide, now), encoding="utf-8")
    for key in PLACEHOLDER_COPY:
        d = out / key
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(placeholder_page(key, now), encoding="utf-8")
    tonight, week = select(events["series"], now)
    return {"out": out, "tonight": len(tonight), "week": sum(len(r) for r in week.values()),
            "tide": "ok" if tide else "unavailable", "tokens": used["tokens"], "icons": used["icons"],
            "art": used["art"]}
