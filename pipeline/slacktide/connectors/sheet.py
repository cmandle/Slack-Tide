"""Published spreadsheet connector: the submission inbox (decision 12).

The public form at /add/ posts into a Google Form whose responses sheet is published to the
web as CSV. This connector reads that CSV. Columns are found by their header words, so the
form's questions can be reworded without touching code; the words below are what each
column header must contain (case does not matter).

Every row becomes one occurrence under source ``submissions``. Nothing from here publishes
without the approver, so the source never carries ``review: auto``. Organiser names and
email addresses stay in the sheet: they are never copied into a record.
"""
from __future__ import annotations
import csv, io
from datetime import datetime, timedelta
from dateutil import parser as dtparse
from ..models import Occurrence
from .base import Connector

COLUMNS = {
    "title": ("title", "event name", "name of the event", "what"),
    "date": ("date",),
    "start": ("start", "time"),
    "end": ("end",),
    "venue": ("venue", "where", "location", "place"),
    "town": ("town", "city"),
    "url": ("link", "url", "website", "web"),
    "cost": ("cost", "price", "admission"),
    "description": ("description", "details", "about"),
    "status": ("status",),
    "stamp": ("timestamp", "submitted"),
}
SKIP_STATUSES = {"withdrawn", "cancelled", "canceled", "spam", "duplicate", "no"}


def map_columns(headers: list[str]) -> dict[str, int]:
    """Our field name to column index. The order matters: 'stamp' claims 'Timestamp' before
    'start' can reach it through the word 'time', and 'end' is matched before 'start' so 'End
    time' does not land on the start column the same way."""
    out: dict[str, int] = {}
    lower = [h.strip().lower() for h in headers]
    for field in ("stamp", "end", "start", "title", "date", "venue", "town", "url", "cost", "description", "status"):
        for i, h in enumerate(lower):
            if i in out.values():
                continue
            if any(w in h for w in COLUMNS[field]):
                out[field] = i
                break
    return out


class SheetConnector(Connector):
    def fetch(self) -> list[Occurrence]:
        if not self.source.get("url"):
            raise ValueError(f"{self.id}: no published CSV address in sources.yaml yet")
        occs = self.parse(self.fetch_text(self.source["url"]))
        return [o for o in occs if o.start <= self.horizon and o.start >= self.now - timedelta(days=1)]

    def parse(self, text: str) -> list[Occurrence]:
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return []
        cols = map_columns(rows[0])
        if "title" not in cols or "date" not in cols:
            raise ValueError(f"{self.id}: the sheet needs a title column and a date column; headers were {rows[0]}")

        def cell(row: list[str], field: str) -> str:
            i = cols.get(field)
            return row[i].strip() if i is not None and i < len(row) else ""

        out: list[Occurrence] = []
        for n, row in enumerate(rows[1:], start=2):
            title, day = cell(row, "title"), cell(row, "date")
            if not title or not day or cell(row, "status").lower() in SKIP_STATUSES:
                continue
            start_t, end_t = cell(row, "start"), cell(row, "end")
            try:
                start = dtparse.parse(f"{day} {start_t}".strip(), fuzzy=True)
            except (ValueError, OverflowError):
                continue
            start = start.replace(tzinfo=self.tz) if start.tzinfo is None else start.astimezone(self.tz)
            end = None
            if end_t:
                try:
                    end = dtparse.parse(f"{day} {end_t}", fuzzy=True).replace(tzinfo=self.tz)
                    if end < start:
                        end += timedelta(days=1)
                except (ValueError, OverflowError):
                    end = None
            uid = f"{cell(row, 'stamp') or n}|{title}"
            out.append(Occurrence(
                source_id=self.id, source_uid=uid, title=title, start=start, end=end,
                all_day=not start_t, venue_raw=cell(row, "venue"), town=cell(row, "town"),
                url=cell(row, "url"), description=cell(row, "description"), cost=cell(row, "cost"),
                source_categories=[]))
        return out
