"""iCalendar connector, built for CivicPlus municipal calendars but generic.

CivicPlus pattern: /common/modules/iCalendar/iCalendar.aspx?catID={cat}&feed=calendar
Observed (2026-10-11): Tiverton cat 14 = 43 rows, mostly public holidays; cat 24 = 243 rows
of senior-centre programme through Feb 2027. Dartmouth cat 14 = 21, cat 24 = 1. Somerset
cat 14 = 5, cat 23 = 5. All other catIDs 0 to 40 returned empty. Category IDs are discovered
per town and declared in sources.yaml.

LOCATION on CivicPlus is HTML: '<p>Dining Room</p> - 34 Roosevelt Avenue Tiverton RI 02878',
'- Tiverton RI 02878' (no room, no street), '<p>VIA ZOOM</p><p><a href=...>...</a></p>'.
See split_location.
"""
from __future__ import annotations
import re
from datetime import datetime, date, time
from icalendar import Calendar
from ..models import Occurrence
from ..normalize import strip_html
from .base import Connector

_WS = re.compile(r"\s+")
_STREET = re.compile(r"^\d+[A-Za-z]?\s")
_SEP = re.compile(r"(?:^|\s)-\s+")

def split_location(loc: str) -> tuple[str, str]:
    """Return (venue, note) from an iCal LOCATION.

    CivicPlus writes 'room or note - street address town ST zip'. The street address is the venue
    when it has a street number; 'Tiverton RI 02878' on its own is not a place and becomes ''.
    The room or note is returned separately for the description. A location with no ' - '
    separator (other producers, or a plain 'Tiverton Senior Center') is the venue as given."""
    text = _WS.sub(" ", strip_html(loc or "")).strip()
    if not text:
        return "", ""
    parts = _SEP.split(text, maxsplit=1)
    if len(parts) == 1:
        return text, ""
    note, addr = parts[0].strip(), parts[1].strip()
    venue = addr if _STREET.match(addr) else ""
    return venue, note

class ICalConnector(Connector):
    def fetch(self) -> list[Occurrence]:
        out: list[Occurrence] = []
        cats = self.source.get("categories") or [None]
        for cat in cats:
            url = self.source["url"].format(cat=cat) if cat is not None else self.source["url"]
            text = self.fetch_text(url)
            out.extend(self.parse(text, suffix=f":{cat}" if cat is not None else ""))
        return out

    def parse(self, text: str, suffix: str = "") -> list[Occurrence]:
        out: list[Occurrence] = []
        cal = Calendar.from_ical(text)
        for comp in cal.walk("VEVENT"):
            start, all_day = self._dt(comp.get("DTSTART"))
            if start is None or not self.in_window(start):
                continue
            end, _ = self._dt(comp.get("DTEND"))
            uid = str(comp.get("UID") or f"{comp.get('SUMMARY')}@{start.isoformat()}")
            venue, note = split_location(str(comp.get("LOCATION") or ""))
            desc = str(comp.get("DESCRIPTION") or "")
            if note:
                desc = f"Location: {note}. {desc}".strip()
            out.append(Occurrence(
                source_id=self.id, source_uid=uid + suffix,
                title=str(comp.get("SUMMARY") or ""),
                start=start, end=end, all_day=all_day,
                venue_raw=venue, town=self.town,
                url=str(comp.get("URL") or ""),
                description=desc,
            ))
        return out

    def _dt(self, prop):
        if prop is None:
            return None, False
        v = prop.dt
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=self.tz)
            return v.astimezone(self.tz), False
        if isinstance(v, date):
            return datetime.combine(v, time(0, 0), tzinfo=self.tz), True
        return None, False
