"""Normalisation: HTML stripping, entity decoding, venue canonicalisation, town resolution,
holiday and closure filter, and a first-pass rule classifier. The LLM classifier replaces
classify() later; the rest stays."""
from __future__ import annotations
import html, re
from rapidfuzz import fuzz, process
from .config import TOWNS, ZIP_TO_TOWN, TOWN_ALIASES, HOLIDAY_TITLES, CLOSURE_PATTERNS, CATEGORIES, canonical_category
from .models import Occurrence

_WS = re.compile(r"\s+")
_BLOCK_TAG = re.compile(r"</?(p|br|div|li|ul|ol|h[1-6]|tr|td|th|table|blockquote)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
# Applied after clean_text, so dashes are already ASCII.
_VENUE_STRIP = re.compile(r"^(the)\s+|,?\s*(inc\.?|llc|ltd\.?)$|\s*-\s*(parish hall|main hall)$", re.I)
_TOWN_ALT = "|".join(re.escape(t.lower()) for t in sorted(TOWNS, key=len, reverse=True))
# "Narrows Center For The Arts Fall River MA" and "Narrows Center for the Arts" are one place.
_VENUE_TOWN_SUFFIX = re.compile(r",?\s+(" + _TOWN_ALT + r")\s*,?\s*(ma|ri|massachusetts|rhode island)?\s*(\d{5})?\s*$")
# A street address written into the venue name: "Gallery X 169 William Street", "New Bedford Art
# Museum, 608 Pleasant St.", "Speakeasy @ The Z! - 984 Purchase St". AHA! Night's cards do this
# for every venue (2026-11-08). The name is the place; the address goes to venues.yaml.
_VENUE_ADDRESS_SUFFIX = re.compile(
    r"[\s,-]+\d{1,5}[a-z]?\s+(?:[a-z0-9.']+\s+){0,3}?"
    r"(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd|way|highway|hwy|route|rte|place|pl|square|sq|court|ct|terrace|ter|wharf|pier)\b\.?.*$")
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

_SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
# Two-letter words that are words, not acronyms: capitalised like any other word.
_TWO_LETTER_WORDS = {"is", "it", "be", "if", "so", "up", "no", "my", "we", "us", "me", "do", "go", "vs", "am", "he", "oh"}

def uncap(title: str) -> str:
    """Theatre marketing shouts: 'MYSTIC PIZZA: A NEW MUSICAL', 'GET THE LED OUT'. When a title
    has no lowercase letter at all, words of four letters or more are title-cased and the small
    words lowered; short words stay as they are, so 'NBSO' and 'DJ' survive. Mixed-case titles
    are left alone."""
    letters = [c for c in title if c.isalpha()]
    words = title.split(" ")
    if len(letters) < 4 or len(words) < 2 or any(c.islower() for c in letters):
        return title          # too short to judge, a lone acronym ("NBSO"), or already mixed case
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^A-Za-z]", "", w)
        after_break = i == 0 or words[i - 1].endswith((":", "-", "!", "?", "."))
        if core.lower() in _SMALL_WORDS and not after_break:
            out.append(w.lower())
        elif len(core) >= 3 or core.lower() in _SMALL_WORDS or core.lower() in _TWO_LETTER_WORDS:
            out.append("'".join(p.capitalize() for p in w.split("'")))
        else:
            out.append(w)     # other one- and two-letter words stay: DJ, TV, NB
    return " ".join(out)

def venue_key(v: str) -> str:
    v = clean_text(v).lower()
    v = _VENUE_STRIP.sub("", v)
    stripped = _VENUE_ADDRESS_SUFFIX.sub("", v)
    if stripped.strip(" ,-"):            # a bare address ("1265 Purchase Street") keeps its key
        v = stripped
    v = _VENUE_TOWN_SUFFIX.sub("", v)
    v = re.sub(r"[^a-z0-9 ]+", " ", v)
    return _WS.sub(" ", v).strip()

def venue_aliases(venues: list[dict]) -> dict[str, str]:
    """venues.yaml as a lookup: the key of the canonical name and of every alias, each to the
    canonical name. The name itself is an alias of itself, so a source that already spells it
    right still lands on the entry."""
    out: dict[str, str] = {}
    for v in venues:
        for raw in [v["name"]] + list(v.get("aliases") or []):
            k = venue_key(str(raw))
            if k:
                out[k] = v["name"]
    return out

class VenueCanon:
    """Maps raw venue strings to one canonical display name per real place.
    Observed collisions: 'Gallery X' vs 'Gallery X, Inc'; 'First Unitarian Church in New Bedford'
    vs 'The First Unitarian Church in New Bedford' vs '... - Parish Hall'. An alias table from
    venues.yaml wins over the fuzzy match and over first-seen spelling: the file's name is the
    display name, which is also what the series id hashes, so renaming a place there is a
    deliberate act that sends its series back through review."""
    THRESHOLD = 92

    def __init__(self, aliases: dict[str, str] | None = None):
        self.aliases = aliases or {}
        self.canon: dict[str, str] = {}   # key -> display

    def resolve(self, raw: str) -> str:
        raw = clean_text(raw)
        if not raw:
            return ""
        k = venue_key(raw)
        if not k:
            return raw
        if k in self.aliases:
            self.canon[k] = self.aliases[k]
            return self.canon[k]
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

# Rules over the seven categories in config.CATEGORIES (the editors' taxonomy, 2026-11-22).
# Order matters: earlier rules win, so the specific comes before the general. A category may
# appear twice: Community's civic words and Learn's library words sit high because a title such
# as "Planning Board walk-through" or "Library craft hour" belongs to the institution; Nightlife's
# activity nouns (karaoke, trivia, tasting) come before Arts' broad ones (play, art, dance); and
# Community's social words and Learn's generic class words sit low so they only catch what no
# stronger word did. Every category name here must be in config.CATEGORIES; _check() enforces it.
_RULES = [
    ("Fundraisers", r"\b(fundrais\w*|benefit|charity|donat\w*|gala|raffle|auction|telethon|bake sale|(food|coat|toy|blood|book) drive|pancake breakfast|spaghetti (supper|dinner)|ham and bean)\b"),
    ("Community", r"\b(select ?board|town (council|meeting|hall)|city council|planning board|zoning|board of|commission(ers)?|committee|probate court|public hearing|town clerk|dpw|council on aging)\b"),
    ("Community", r"\b(volunteer\w*|cleanup|clean-up|stewards?|worship|service|blessing|church|parish|synagogue|prayer|kids?|children|toddler|family|teen|youth|storywalk|zoo|seniors?|bingo|potluck|meetup|meet-up|support group|coffee hour|neighbo(u)?rhood|residents?)\b"),
    ("Learn", r"\b(story ?time|story hour|book (club|talk|group)|author (talk|visit)|library|lifelong learning|lecture|history|historical|talk|panel|discussion|genealogy|tutoring)\b"),
    ("Seasonal", r"\b(festival|feast|parade|\w*fest|illumination|fireworks|holiday|christmas|hanukkah|halloween|trunk or treat|haunted|pumpkin|easter|egg hunt|tree lighting|santa|carol\w*|harvest|farmers'? market|market|fair|bazaar|craft (show|fair)|flea|swap|first night|new year)\b"),
    ("Active", r"\b(hike|walk|trail|birds?|birding|paddle|kayak|beach|garden|reserve|woods|marsh|yoga|fitness|run|5k|race|regatta|sailing|pickleball|basketball|swim|balance and mobility|bike|ride|cycling|tai chi|pilates|zumba|surf|skate|tennis|golf|soccer|softball|bowling|workout|stretch|outdoors?|nature)\b"),
    ("Nightlife", r"\b(open mic|karaoke|jam|band|live music|singer|dj|bluegrass|jazz|trivia|comedy|cabaret|pub|bar|brewery|taproom|tap room|winery|wine|beer|cocktails?|happy hour|tasting|dinner|brunch|food truck|supper|late night|dance party)\b"),
    ("Arts", r"\b(theatre|theater|play|musical|shakespeare|dance|drawing|sketch|studio|printmaking|pottery|clay|gallery|art|arts|exhibit(ion)?|museum|opening night|concert|orchestra|symphony|choir|chorus|choral|opera|recital|film|cinema|movie|poetry)\b"),
    ("Learn", r"\b(workshop|class|course|clinic|training|seminar|session|tour|webinar|stem)\b"),
]
_COMPILED = [(c, re.compile(p, re.I)) for c, p in _RULES]

def _check():
    bad = sorted({c for c, _ in _RULES} - set(CATEGORIES))
    if bad:
        raise ValueError(f"normalize._RULES names categories outside config.CATEGORIES: {bad}")
_check()

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
              default_venue_by_source: dict[str, str] | None = None,
              default_category_by_source: dict[str, str] | None = None,
              venue_alias_table: dict[str, str] | None = None) -> list[Occurrence]:
    """Clean every occurrence in place. `default_venue_by_source` fills the venue for
    single-venue sources whose feed carries none (Brownell Library sends "venue": []).
    `default_category_by_source` is our own call for a single-purpose venue (a theatre is
    Arts & Theatre) when the rule classifier finds nothing; it is never the source's category.
    A category the connector has already set (the recurring connector carries the editor's own
    call) is kept. `venue_alias_table` is venue_aliases(venues.yaml): the spellings we have
    already matched to a real place."""
    canon = VenueCanon(venue_alias_table)
    default_venue_by_source = default_venue_by_source or {}
    default_category_by_source = default_category_by_source or {}
    for o in occs:
        o.title = uncap(clean_text(o.title))
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
        o.category = (canonical_category(o.category)               # already decided by the connector (a declared schedule's editor)
                      or classify(o.title, o.venue, o.description)
                      or next((canonical_category(c) for c in o.source_categories if canonical_category(c)), "")   # a source naming OUR category (the /add/ form does), old names included
                      or canonical_category(default_category_by_source.get(o.source_id, "")))
    return occs
