"""Write the published artifact: data/events.json plus a run report."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .models import Series

def write(series: list[Series], report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "series_count": len(series),
        "occurrence_count": sum(s.count for s in series),
        "series": [s.to_dict() for s in series],
    }
    p = out_dir / "events.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "run-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
