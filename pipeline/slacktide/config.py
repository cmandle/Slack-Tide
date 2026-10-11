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

def load_sources(path: Path | None = None) -> list[dict]:
    p = path or Path(__file__).with_name("sources.yaml")
    with open(p, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or []
    for s in sources:
        s.setdefault("enabled", True)
        s.setdefault("role", "primary")
    return sources
