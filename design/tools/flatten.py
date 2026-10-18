#!/usr/bin/env python3
"""Flatten a Design-canvas artboard (.dc.html) into plain static HTML.

The canvas files under design/canvas/ use a small template runtime:
<sc-for> loops, <sc-if> branches and {{dotted.holes}} filled from the
renderVals() method of the Component class in each file. This script runs
renderVals() with node, expands the template in Python, strips the runtime
wrapper, and writes a self-contained page that opens in any browser.

Usage:
    python3 design/tools/flatten.py design/canvas/Revision-Phone.dc.html design/reference/phone.html

Requires python3 and node on PATH. Uploaded canvas assets referenced as
/_blob/<id> are mapped to design/reference/assets/ through ASSETS below.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ASSETS = {
    # the one photograph stand-in, shown with the halftone treatment
    "6b3c030ada2b926f2c8f42da495df9f1": "assets/harbor.jpg",
    # card illustrations from design/art/, shown as drawn
    "6d579f224a254e1cf80daf4901b3f7ad": "../art/music-1.svg",
    "fa44977142b21a8f508d62aea88ef582": "../art/arts-1.svg",
    "653a020204c58a940d733b3b1cadff48": "../art/outdoors-2.svg",
    "b41d7f4e50ae2633b43a25c7051c45cb": "../art/family-2.svg",
}


def render_vals(src: str) -> dict:
    """Run the artboard's renderVals() in node with its data-props defaults."""
    m = re.search(r"<script type=\"text/x-dc\" data-dc-script data-props='(.*?)'>(.*?)</script>", src, re.S)
    if not m:
        raise SystemExit("no data-dc-script block found")
    props_json, logic = m.group(1), m.group(2)
    props_json = props_json.replace("&amp;", "&").replace("&#39;", "'")
    props = {k: v.get("default") for k, v in json.loads(props_json).items() if isinstance(v, dict) and "default" in v}
    program = (
        "class DCLogic { constructor() { this.props = {}; } }\n"
        + logic
        + "\nconst c = new Component(); c.props = "
        + json.dumps(props)
        + ";\nprocess.stdout.write(JSON.stringify(c.renderVals()));\n"
    )
    out = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def lookup(ctx: dict, path: str):
    cur = ctx
    for part in path.strip().split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return ""
    return cur


HOLE = re.compile(r"\{\{\s*([A-Za-z0-9_.$]+)\s*\}\}")
FOR = re.compile(r"<sc-for\s+list=\"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}\"\s+as=\"([A-Za-z0-9_]+)\"[^>]*>(.*?)</sc-for>", re.S)
IF = re.compile(r"<sc-if\s+value=\"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}\"[^>]*>(.*?)</sc-if>", re.S)


def expand(html: str, ctx: dict) -> str:
    def do_for(m):
        items = lookup(ctx, m.group(1)) or []
        name, body = m.group(2), m.group(3)
        return "".join(expand(body, {**ctx, name: item, "$index": i}) for i, item in enumerate(items))

    html = FOR.sub(do_for, html)
    html = IF.sub(lambda m: expand(m.group(2), ctx) if lookup(ctx, m.group(1)) else "", html)
    html = HOLE.sub(lambda m: str(lookup(ctx, m.group(1))), html)
    return html


def flatten(src_path: Path, out_path: Path) -> None:
    src = src_path.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", src, re.S).group(1)
    helmet = re.search(r"<helmet>(.*?)</helmet>", src, re.S).group(1)
    body = re.search(r"</helmet>(.*?)</x-dc>", src, re.S).group(1)
    vals = render_vals(src)
    body = expand(body, vals)
    for blob, rel in ASSETS.items():
        body = body.replace(f"/_blob/{blob}", rel)
    page = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{title}</title>\n{helmet.strip()}\n</head>\n<body>\n{body.strip()}\n</body>\n</html>\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"wrote {out_path} ({len(page)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    flatten(Path(sys.argv[1]), Path(sys.argv[2]))
