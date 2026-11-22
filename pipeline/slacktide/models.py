"""Record shapes. Occurrences are what connectors emit; Series is what we publish."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

@dataclass
class Occurrence:
    source_id: str
    source_uid: str            # the source's own identifier for this occurrence
    title: str
    start: datetime            # timezone-aware
    end: Optional[datetime]
    all_day: bool
    venue_raw: str
    town: str                  # canonical town, or "" if unresolved
    url: str
    description: str = ""
    cost: str = ""
    source_categories: list[str] = field(default_factory=list)
    venue: str = ""            # canonical venue, filled by normalize
    category: str = ""         # platform category, filled by classify
    dropped: str = ""          # reason, if filtered out

    def key(self) -> str:
        return f"{self.source_id}:{self.source_uid}"

@dataclass
class Series:
    id: str
    title: str
    venue: str
    town: str
    category: str              # the primary category: categories[0], or "" when unclassified
    source_id: str
    url: str
    cost: str
    first_start: datetime
    last_start: datetime
    count: int
    cadence: str               # once | daily | weekdays | weekends | weekly | several-a-week | fortnightly | monthly | irregular
    weekday: Optional[int]     # 0 = Monday, for weekly series
    occurrences: list[dict]    # [{start, end, all_day}]
    summary: str = ""          # the first occurrence's description, trimmed, for the reviewer
    categories: list[str] = field(default_factory=list)   # every category, primary first; the classifier gives one, an approver may set several
    approval: str = "pending"  # pending | approved | rejected, set by approval.apply
    decided_by: str = ""       # the approver's name, or "source trust"
    # The approver's edits (approval.apply_edits): the overrides in force, keyed as in
    # config.EDITABLE_FIELDS; the pipeline's own values for those keys; who made them and when.
    edits: dict = field(default_factory=dict)
    original: dict = field(default_factory=dict)
    edited_by: str = ""
    edited_on: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("first_start", "last_start"):
            d[k] = d[k].isoformat()
        return d
