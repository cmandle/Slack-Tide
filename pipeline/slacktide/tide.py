"""Tide predictions for the site's tide panel, from NOAA CO-OPS.

Two requests per run against the CO-OPS data API: the high and low water table (``interval=hilo``)
and the predicted level every 30 minutes (``interval=30``), both for today and tomorrow in local
time. The result is written to ``data/tide.json`` beside ``events.json``. The station is set in
``config.TIDE_STATION``; see the note there on how it was confirmed.

The fetch is best effort. A failure leaves the previous ``tide.json`` in place and the site
generator shows "Tide data unavailable" once that file is older than ``TIDE_MAX_AGE_HOURS``.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from .config import TZ, TIDE_STATION, TIDE_STATION_NAME, TIDE_MAX_AGE_HOURS
from .connectors.base import USER_AGENT

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
DATUM, UNITS = "MLLW", "english"

def _params(begin: datetime, days: int, interval: str) -> dict:
    return {
        "station": TIDE_STATION, "product": "predictions", "datum": DATUM, "units": UNITS,
        "time_zone": "lst_ldt", "format": "json", "interval": interval,
        "begin_date": begin.strftime("%Y%m%d"), "range": str(days * 24),
        "application": "slack-tide.org",
    }

def parse_predictions(text: str) -> list[dict]:
    """CO-OPS returns {"predictions": [{"t": "2026-10-18 01:57", "v": "3.374", "type": "H"}]} or
    {"error": {"message": ...}}. Values are strings; we store floats."""
    body = json.loads(text)
    if "error" in body:
        raise RuntimeError(f"CO-OPS: {body['error'].get('message', body['error'])}")
    out = []
    for p in body.get("predictions", []):
        row = {"t": p["t"], "v": round(float(p["v"]), 2)}
        if p.get("type"):
            row["type"] = p["type"]
        out.append(row)
    return out

def fetch(session: requests.Session | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(ZoneInfo(TZ))
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    s = session or requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    def get(interval):
        r = s.get(API, params=_params(today, 2, interval), timeout=30)
        r.raise_for_status()
        return parse_predictions(r.text)
    return {
        "station": TIDE_STATION, "station_name": TIDE_STATION_NAME,
        "datum": DATUM, "units": "ft", "time_zone": TZ,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "hilo": get("hilo"), "levels": get("30"),
    }

def write(payload: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "tide.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return p

def load(path: Path, now: datetime | None = None, max_age_hours: int = TIDE_MAX_AGE_HOURS) -> dict | None:
    """The tide file if it exists and is fresh enough to show, else None."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    now = now or datetime.now(timezone.utc)
    if now.astimezone(timezone.utc) - fetched.astimezone(timezone.utc) > timedelta(hours=max_age_hours):
        return None
    return payload
