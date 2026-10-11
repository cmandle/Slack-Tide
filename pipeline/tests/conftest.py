import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

@pytest.fixture
def frozen(monkeypatch):
    """Pin 'now' so fixtures dated 2099 fall inside the window."""
    from slacktide.connectors import base
    tz = ZoneInfo("America/New_York")
    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2098, 12, 31, 12, 0, tzinfo=tz)
    monkeypatch.setattr(base, "datetime", _DT)
    return _DT

FIX = pathlib.Path(__file__).parent / "fixtures"
def fixture_text(name): return (FIX / name).read_text(encoding="utf-8")
