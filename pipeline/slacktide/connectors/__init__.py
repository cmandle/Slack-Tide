from .tribe import TribeConnector
from .ical import ICalConnector
from .rss import RSSConnector
from .html import HtmlConnector
from .sheet import SheetConnector
from .recurring import RecurringConnector
from .squarespace import SquarespaceConnector

CONNECTORS = {"tribe": TribeConnector, "ical": ICalConnector, "rss": RSSConnector,
              "html": HtmlConnector, "sheet": SheetConnector, "recurring": RecurringConnector, "squarespace": SquarespaceConnector}

def for_source(source: dict, **kw):
    try:
        cls = CONNECTORS[source["kind"]]
    except KeyError as e:
        raise ValueError(f"unknown connector kind {source.get('kind')!r} for {source.get('id')}") from e
    return cls(source, **kw)
