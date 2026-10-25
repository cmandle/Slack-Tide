"""Static configuration: geography, taxonomy, holiday list."""
from __future__ import annotations
from pathlib import Path
import yaml

TZ = "America/New_York"
WINDOW_DAYS = 60

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

# Aliases that appear in source data for the same town.
TOWN_ALIASES = {
    "new bedford.": "New Bedford", "south dartmouth": "Dartmouth", "north dartmouth": "Dartmouth",
    "westport point": "Westport", "assonet": "Freetown", "east freetown": "Freetown",
    "onset": "Wareham", "adamsville": "Little Compton",
}

# The platform's own taxonomy. Source categories are never trusted; see normalize.classify.
CATEGORIES = [
    "Music", "Arts & Theatre", "Museums & Exhibitions", "Outdoors & Nature", "Family & Children",
    "Library & Talks", "Civic & Town Meetings", "Food & Drink", "Markets & Fairs",
    "Sports & Recreation", "Faith & Spiritual", "Education & Workshops", "Festivals",
    "Volunteering & Causes",
]

# Display families for the Events section. design/DESIGN.md draws seven category tiles plus
# All, with one icon and one colour each (design/reference/icons, design/tokens.css); the
# taxonomy above has fourteen entries, so each entry belongs to a family for the tile row, the
# swatch and the card label. The family slug is the icon file name and the --st-cat-* token.
# Open with the taxonomy issue: whether the taxonomy itself should shrink to these seven.
CATEGORY_FAMILIES = {
    "music": ("Music", ["Music", "Festivals"]),
    "arts": ("Arts", ["Arts & Theatre", "Museums & Exhibitions", "Education & Workshops"]),
    "outdoors": ("Outdoors", ["Outdoors & Nature", "Sports & Recreation"]),
    "family": ("Family", ["Family & Children"]),
    "library": ("Library", ["Library & Talks", "Faith & Spiritual"]),
    "markets": ("Markets", ["Markets & Fairs", "Food & Drink"]),
    "civic": ("Civic", ["Civic & Town Meetings", "Volunteering & Causes"]),
}
CATEGORY_FAMILY_OF = {cat: slug for slug, (_, cats) in CATEGORY_FAMILIES.items() for cat in cats}

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

def load_sources(path: Path | None = None) -> list[dict]:
    p = path or Path(__file__).with_name("sources.yaml")
    with open(p, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or []
    for s in sources:
        s.setdefault("enabled", True)
        s.setdefault("role", "primary")
    return sources
