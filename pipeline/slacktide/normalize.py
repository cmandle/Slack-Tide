"""Normalisation: HTML stripping, entity decoding, venue canonicalisation, town resolution,
holiday and closure filter, and a first-pass rule classifier. The LLM classifier replaces
classify() later; the rest stays."""
from __future__ import annotations
import html, re
from rapidfuzz import fuzz, process
from .config import TOWNS, ZIP_TO_TOWN, TOWN_ALIASES, HOLIDAY_TITLES, CLOSURE_PATTERNS
from .models import Occurrence

_WS = re.compile(r"\s+")
_BLOCK_TAG = re.compile(r"</?(p|br|div|li|ul|ol|h[1-6]|tr|td|th|table|blockquote)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
# Applied after clean_text, so dashes are already ASCII.
_VENUE_STRIP = re.compile(r"^(the)\s+|,?\s*(inc\.?|llc|ltd\.?)$|\s*-\s*(parish hall|main hall)$", re.I)
_TOWN_ALT = "|".join(re.escape(t.lower()) for t in sorted(TOWNS, key=len, reverse=True))
# "Narrows Center For The Arts Fall River MA" and "Narrows Center for the Arts" are one place.
_VENUE_TOWN_SUFFIX = re.compile(r",?\s+(" + _TOWN_ALT + r")\s*,?\s*(ma|ri|massachusetts|rhode island)?\s*(\d{5})?\s*$")
_TOWN_IN_TEXT = re.compile(r"\b(" + _TOWN_ALT + r")\b")
# Curly quotes, dashes and non-breaking spaces to their ASCII equivalents.
_PUNCT = str.maketrans({
    "’": "'", "‘": "'",      # right and left single quotation marks
    "“": '"', "”": '"',      # left and right double quotation marks
    "–": "-", "—": "-",      # en dash, em dash
    " ": " ",                     # no-break space
})
_CLOSURE = [re.compile(p, re.I) for p in CLOSURE_PATTERNS]

def strip_html(s: str) -> str:
    """Drop tags and decode entities. Block-level tags become spaces so words do not run together.
    Observed 2026-10-11: Tribe descriptions are full HTML ('<span class="...">' matched the
    'class' rule and sent most Narrows concerts to Education & Workshops). CivicPlus LOCATION
    fields look like '<p>Dining Room</p> - Tiverton RI 02878'."""
    s = _BLOCK_TAG.sub(" ", s or "")
    s = _TAG.sub("", s)
    return html.unescape(s)

def clean_text(s: str) -> str:
    s = strip_html(s).translate(_PUNCT)
    return _WS.sub(" ", s).strip()

def venue_key(v: str) -> str:
    v = clean_text(v).lower()
    v = _VENUE_STRIP.sub("", v)
    v = _VENUE_TOWN_SUFFIX.sub("", v)
    v = re.sub(r"[^a-z0-9 ]+", " ", v)
    return _WS.sub(" ", v).strip()

class VenueCanon:
    """Maps raw venue strings to one canonical display name per real place.
    Observed collisions: 'Gallery X' vs 'Gallery X, Inc'; 'First Unitarian Church in New Bedford'
    vs 'The First Unitarian Church in New Bedford' vs '... - Parish Hall'."""
    THRESHOLD = 92

    def __init__(self):
        self.canon: dict[str, str] = {}   # key -> display

    def resolve(self, raw: str) -> str:
        raw = clean_text(raw)
        if not raw:
            return ""
        k = venue_key(raw)
        if not k:
            return raw
        if k in self.canon:
            return self.canon[k]
        if self.canon:
            match = process.extractOne(k, list(self.canon.keys()), scorer=fuzz.token_sort_ratio)
            if match and match[1] >= self.THRESHOLD:
                self.canon[k] = self.canon[match[0]]
                return self.canon[k]
        self.canon[k] = raw
        return raw

def town_in_text(s: str) -> str:
    """A town name appearing in a venue string ('Fall River Public Library'), else ''."""
    m = _TOWN_IN_TEXT.search(clean_text(s).lower())
    if not m:
        return ""
    return next(t for t in TOWNS if t.lower() == m.group(1))

def resolve_town(raw_city: str, default: str, hint: str = "") -> str:
    """Canonical town from the record's city field. With no city, a town named in `hint`
    (the venue) beats the source default: Viva Fall River lists the New Bedford Whaling Museum."""
    c = clean_text(raw_city).lower().rstrip(".")
    if not c:
        return town_in_text(hint) or default
    if c in ZIP_TO_TOWN:
        return ZIP_TO_TOWN[c]
    if c in TOWN_ALIASES:
        return TOWN_ALIASES[c]
    for t in TOWNS:
        if c == t.lower():
            return t
    m = process.extractOne(c, [t.lower() for t in TOWNS], scorer=fuzz.ratio)
    if m and m[1] >= 90:
        return TOWNS[[t.lower() for t in TOWNS].index(m[0])]
    return default

def is_holiday(title: str) -> bool:
    t = clean_text(title).lower()
    return t in HOLIDAY_TITLES or any(t.startswith(h + " ") for h in ("early voting", "polls open"))

def is_closure(title: str) -> bool:
    """Closures and election administration are not events: 'Library Closed', 'Eary Voting' (sic),
    'Last Day to Register to Vote', 'Advanced Processing for November 3rd State Election'."""
    t = clean_text(title)
    return any(rx.search(t) for rx in _CLOSURE)

_RULES = [
    ("Civic & Town Meetings", r"\b(select ?board|town (council|meeting|hall)|planning board|zoning|board of|commission(ers)?|committee|probate court|public hearing|town clerk|dpw)\b"),
    ("Library & Talks", r"\b(story ?time|story hour|book (club|talk|group)|author (talk|visit)|library|lifelong learning|lecture)\b"),
    ("Family & Children", r"\b(kids?|children|toddler|family|teen|youth|storywalk|trunk or treat|zoo)\b"),
    ("Outdoors & Nature", r"\b(hike|walk|trail|birds?|birding|paddle|kayak|beach|garden|reserve|woods|marsh|cleanup|stewards?)\b"),
    ("Markets & Fairs", r"\b(farmers'? market|market|fair|bazaar|craft (show|fair)|flea|swap)\b"),
    ("Food & Drink", r"\b(tasting|dinner|brunch|brewery|winery|wine|beer|oktoberfest|food truck|bake sale|supper|pancake)\b"),
    ("Music", r"\b(concert|open mic|karaoke|jam|band|choir|chorus|choral|orchestra|symphony|live music|singer|dj|bluegrass|jazz)\b"),
    ("Arts & Theatre", r"\b(theatre|theater|play|musical|shakespeare|dance|drawing|sketch|studio|printmaking|pottery|clay|gallery|art)\b"),
    ("Museums & Exhibitions", r"\b(exhibit(ion)?|museum|opening night|tour)\b"),
    ("Festivals", r"\b(festival|feast|parade|fest\b|illumination|fireworks)\b"),
    ("Sports & Recreation", r"\b(yoga|fitness|run|5k|race|regatta|sailing|bingo|pickleball|basketball|swim|balance and mobility)\b"),
    ("Education & Workshops", r"\b(workshop|class|course|clinic|training|seminar|session)\b"),
    ("Faith & Spiritual", r"\b(mass|worship|service|blessing|church|parish|synagogue|prayer)\b"),
    ("Volunteering & Causes", r"\b(volunteer|fundrais|donat|charity|benefit)\b"),
]
_COMPILED = [(c, re.compile(p, re.I)) for c, p in _RULES]

def classify(title: str, venue: str, description: str = "") -> str:
    """Rule classifier over the platform taxonomy. Order matters: earlier rules win.
    Source categories are deliberately ignored: Explore New Bedford's top two are 'Free' and 'Downtown'.
    All three inputs are stripped of HTML first; see strip_html."""
    # Title is the strongest signal, then venue, then the first part of the description.
    # Scoring them in that order stops a venue name ("... Garden Museum") outranking the title.
    for text in (clean_text(title), clean_text(venue), clean_text(description)[:400]):
        for cat, rx in _COMPILED:
            if text and rx.search(text):
                return cat
    return ""

def normalize(occs: list[Occurrence], default_town_by_source: dict[str, str],
              default_venue_by_source: dict[str, str] | None = None) -> list[Occurrence]:
    """Clean every occurrence in place. `default_venue_by_source` fills the venue for
    single-venue sources whose feed carries none (Brownell Library sends "venue": [])."""
    canon = VenueCanon()
    default_venue_by_source = default_venue_by_source or {}
    for o in occs:
        o.title = clean_text(o.title)
        o.description = clean_text(o.description)
        o.venue_raw = clean_text(o.venue_raw) or default_venue_by_source.get(o.source_id, "")
        o.venue = canon.resolve(o.venue_raw)
        o.town = resolve_town(o.town, default_town_by_source.get(o.source_id, ""), hint=o.venue_raw)
        if is_holiday(o.title):
            o.dropped = "holiday"
            continue
        if is_closure(o.title):
            o.dropped = "closure"
            continue
        if not o.title:
            o.dropped = "no title"
            continue
        o.category = classify(o.title, o.venue, o.description)
    return occs
