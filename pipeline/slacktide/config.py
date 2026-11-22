"""Static configuration: geography, taxonomy, holiday list."""
from __future__ import annotations
from pathlib import Path
import yaml

TZ = "America/New_York"
WINDOW_DAYS = 90   # was 60 until 2026-11-08; venues such as the Zeiterion list a season ahead

# Canonical town list. Order is presentation order.
TOWNS = [
    "New Bedford", "Fall River", "Dartmouth", "Fairhaven", "Acushnet", "Westport",
    "Somerset", "Swansea", "Freetown", "Mattapoisett", "Marion", "Rochester", "Wareham",
    "Tiverton", "Little Compton",
]

# ZIP codes seen in venue city fields, mapped to towns.
ZIP_TO_TOWN = {
    "02740": "New Bedford", "02741": "New Bedford", "02742": "New Bedford", "02744": "New Bedford",
    "02745": "New Bedford", "02746": "New Bedford", "02720": "Fall River", "02721": "Fall River",
    "02723": "Fall River", "02724": "Fall River", "02747": "Dartmouth", "02748": "Dartmouth",
    "02719": "Fairhaven", "02743": "Acushnet", "02790": "Westport", "02791": "Westport",
    "02726": "Somerset", "02777": "Swansea", "02702": "Freetown", "02717": "Freetown",
    "02739": "Mattapoisett", "02738": "Marion", "02770": "Rochester", "02571": "Wareham",
    "02558": "Wareham", "02878": "Tiverton", "02837": "Little Compton",
}

# Town centres for the map: where a listing sits when its venue has no coordinates in
# venues.yaml. Village centres by hand (2026-11-08), not geocoded; a pin here is marked
# approximate on the page.
TOWN_CENTERS = {
    "New Bedford": (41.6356, -70.9270), "Fall River": (41.7015, -71.1550), "Dartmouth": (41.6128, -70.9545),
    "Fairhaven": (41.6376, -70.9036), "Acushnet": (41.6806, -70.9078), "Westport": (41.5867, -71.0817),
    "Somerset": (41.7701, -71.1287), "Swansea": (41.7482, -71.1898), "Freetown": (41.7898, -71.0600),
    "Mattapoisett": (41.6584, -70.8161), "Marion": (41.7001, -70.7628), "Rochester": (41.7318, -70.8206),
    "Wareham": (41.7612, -70.7198), "Tiverton": (41.6259, -71.1866), "Little Compton": (41.5093, -71.1631),
}

# Aliases that appear in source data for the same town.
TOWN_ALIASES = {
    "new bedford.": "New Bedford", "south dartmouth": "Dartmouth", "north dartmouth": "Dartmouth",
    "westport point": "Westport", "assonet": "Freetown", "east freetown": "Freetown",
    "onset": "Wareham", "adamsville": "Little Compton",
}

# The platform's own taxonomy, settled by the editors on 2026-11-22: seven categories, in
# presentation order. This list is the one place the taxonomy lives. The rule classifier
# (normalize.classify), the planned Haiku classifier, the /add/ form, the admin page's category
# selects, the category tiles, the card labels, the swatch colours and the card illustrations
# all read it. Source categories are never trusted; see normalize.classify.
CATEGORIES = ["Nightlife", "Active", "Arts", "Learn", "Seasonal", "Fundraisers", "Community"]

# The slug of a category is its icon file name (design/reference/icons/<slug>.svg), its
# --st-cat-<slug> colour token (design/tokens.css), its art scene prefix (design/art/<slug>-N.svg)
# and the data-cat value the tiles filter on. One per category since the taxonomy shrank to the
# seven tiles; CATEGORY_FAMILIES keeps the (label, [categories]) shape the build reads.
CATEGORY_SLUG = {c: c.lower() for c in CATEGORIES}
CATEGORY_FAMILIES = {CATEGORY_SLUG[c]: (c, [c]) for c in CATEGORIES}
CATEGORY_FAMILY_OF = {cat: slug for slug, (_, cats) in CATEGORY_FAMILIES.items() for cat in cats}

# Where the fourteen categories of the first taxonomy (2026-09 to 2026-11-22) went. Read by
# canonical_category() so a category written under the old names, in a submission sheet row
# or an approvals.yaml entry, still lands on one of the seven. Series ids do not hash the
# category (series.py), so the rename invalidated no approval.
CATEGORY_RENAMES = {
    "Music": "Nightlife",
    "Food & Drink": "Nightlife",
    "Outdoors & Nature": "Active",
    "Sports & Recreation": "Active",
    "Arts & Theatre": "Arts",
    "Museums & Exhibitions": "Arts",
    "Library & Talks": "Learn",
    "Education & Workshops": "Learn",
    "Markets & Fairs": "Seasonal",
    "Festivals": "Seasonal",
    "Volunteering & Causes": "Community",
    "Civic & Town Meetings": "Community",
    "Family & Children": "Community",
    "Faith & Spiritual": "Community",
}

def canonical_category(name: str) -> str:
    """One of CATEGORIES for a category name as written: exact, case-insensitive, or one of the
    first taxonomy's names. Anything else is ''."""
    s = str(name or "").strip()
    if not s:
        return ""
    for c in CATEGORIES:
        if s.lower() == c.lower():
            return c
    return CATEGORY_RENAMES.get(s, "")

def canonical_categories(values) -> list[str]:
    """A series' category list from names as written: a list, or one string with commas. Each
    name goes through canonical_category; unknown names and repeats are dropped, order kept.
    The first entry is the primary category (the card colour, the illustration, the tile)."""
    if isinstance(values, str):
        values = values.split(",")
    out: list[str] = []
    for v in values or []:
        c = canonical_category(v)
        if c and c not in out:
            out.append(c)
    return out[:len(CATEGORIES)]

def canonical_town(name: str) -> str:
    """One of TOWNS for a town as written, case-insensitively, aliases included; else ''."""
    s = str(name or "").strip()
    if not s:
        return ""
    for t in TOWNS:
        if s.lower() == t.lower():
            return t
    return TOWN_ALIASES.get(s.lower(), "")

# What an approver may change on a series through an approvals.yaml entry (approval.apply_edits):
# the display fields, and the category list. Keys are the names the entry, the admin page, the
# Worker and `slacktide approve --set` all use; the value is the series record field each lands on.
# Every one is safe to edit: the overrides are applied after the series id is computed, so the id
# (source, title, venue as the source spells them) never moves and the approval holds.
EDITABLE_FIELDS = {"title": "title", "venue": "venue", "town": "town", "description": "summary",
                   "cost": "cost", "url": "url", "categories": "categories"}
EDIT_MAX_LENGTH = {"title": 300, "venue": 300, "town": 60, "description": 2000, "cost": 120, "url": 500}

# Municipal feeds carry public holidays as events. These are dropped.
HOLIDAY_TITLES = {
    "new year's day", "new years day", "martin luther king day", "martin luther king jr. day",
    "mlk day", "presidents day", "presidents' day", "washington's birthday", "patriots day",
    "patriots' day", "memorial day", "juneteenth", "independence day", "labor day",
    "columbus day", "indigenous peoples day", "indigenous peoples' day", "veterans day",
    "veterans' day", "thanksgiving", "thanksgiving day", "day after thanksgiving", "christmas",
    "christmas day", "christmas eve", "new year's eve", "victory day", "good friday", "easter",
    "halloween", "town hall closed", "offices closed", "early voting", "state election",
}

# Closures and election administration published as calendar items. Matched case-insensitively
# against the cleaned title; see normalize.is_closure. "Eary Voting" is a real Dartmouth typo.
CLOSURE_PATTERNS = [
    r"\bclosed\b", r"\b(early|eary) voting\b", r"\bpolls? (open|close)\b", r"\bregister to vote\b",
    r"\bvoter registration\b", r"\b(state|town|general|primary) election\b", r"\belection day\b",
    r"\babsentee ballot\b", r"\badvanced? processing\b", r"\btrash (delay|schedule|pickup)\b",
]

# Tide panel. NOAA CO-OPS tide prediction station, confirmed against the CO-OPS metadata API on
# 2026-10-25: 8447636 "New Bedford Harbor, Marine Terminal" is a harmonic (reference) station
# inside the hurricane barrier; 8447712 "Clarks Point" is the reference station just outside
# it and reads within a few tenths of a foot. The panel showed 8447386 "Fall River" (head of
# Mount Hope Bay) until 2026-10-25; CO-OPS lists no "Fall River entrance". Subordinate stations
# for the other towns (Mattapoisett 8447531, Marion 8447385, Onset 8447277, Westport Harbor
# 8447975, Sakonnet 8450768) are there when the panel becomes per-town. Datum MLLW, feet,
# local time.
TIDE_STATION = "8447636"
TIDE_STATION_NAME = "New Bedford Harbor"
TIDE_MAX_AGE_HOURS = 24

# Provenance line on every published card. Sources may override with a `provenance:` key in
# sources.yaml; the default is the human review step every record passes through.
PROVENANCE_DEFAULT = "Read by a person"

ROOT = Path(__file__).resolve().parents[2]
VENUES_PATH = ROOT / "venues.yaml"

def load_venues(path: Path | None = None) -> list[dict]:
    """venues.yaml at the repository root: one entry per real place with its canonical name,
    town, address, coordinates and the raw spellings sources use for it. The normaliser reads
    the aliases, the map reads the coordinates. A missing file is an empty list, so the pipeline
    runs on a checkout without it."""
    p = path or VENUES_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        rows = yaml.safe_load(f) or []
    return [v for v in rows if isinstance(v, dict) and v.get("id") and v.get("name")]

def load_sources(path: Path | None = None) -> list[dict]:
    p = path or Path(__file__).with_name("sources.yaml")
    with open(p, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or []
    for s in sources:
        s.setdefault("enabled", True)
        s.setdefault("role", "primary")
    return sources
