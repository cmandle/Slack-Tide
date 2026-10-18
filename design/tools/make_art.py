#!/usr/bin/env python3
"""Generate the card illustration set under design/art/.

Flat-shape scenes in the Fumayo palette, three per category family plus three
general ones, each a self-contained SVG with a grain filter. Family slugs match
pipeline.slacktide.config.CATEGORY_FAMILIES and the --st-cat-* tokens. The site
uses them as the card image when a series has no organiser photo:
design/DESIGN.md, Images.

    python3 design/tools/make_art.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "art"
W, H = 900, 640

P = dict(
    paper="#F6F1EE", ink="#1A1A1A", white="#FBF8F5",
    sky="#DCE9F0", dusk="#FFD9A8", night="#34507A", cream="#F2E8D8",
    sea="#86B2CB", seadark="#5F8FA8", sand="#F0DFBD",
    grass="#6CCB77", grassdark="#3E9A52", coral="#FF6B6C", yellow="#FFEF6B",
    lilac="#C9A7E3", lilacdark="#9C76C2", tangerine="#FFA657", tangdark="#E07E2F",
    slate="#B8C7D1", slatedark="#6E8494", brown="#8A6A2F", tan="#C9A26B",
)


def rect(x, y, w, h, c):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c}"/>'


def circle(cx, cy, r, c):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{c}"/>'


def poly(points, c):
    pts = " ".join(f"{x},{y}" for x, y in points)
    return f'<polygon points="{pts}" fill="{c}"/>'


def line(x1, y1, x2, y2, c, w=6):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>'


def path(d, c, w=6, fill="none"):
    return f'<path d="{d}" fill="{fill}" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'


def posts(xs, y0, y1, w, c):
    return "".join(rect(x, y0, w, y1 - y0, c) for x in xs)


def bulbs(x0, x1, y, n, c, sag=28):
    out = [path(f"M{x0} {y} Q{(x0 + x1) / 2} {y + sag * 2} {x1} {y}", P["ink"], 3)]
    for i in range(n):
        t = i / (n - 1)
        x = x0 + (x1 - x0) * t
        yy = y + 4 * sag * t * (1 - t)
        out.append(circle(x, yy + 10, 9, c))
    return "".join(out)


def trees(xs, base, h, c, w=52):
    return "".join(poly([(x, base), (x + w, base), (x + w / 2, base - h)], c) for x in xs)


def scene(name, label, sky, body, seed):
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">'
        f'<defs><filter id="grain" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="{seed}" result="t"/>'
        f'<feColorMatrix in="t" type="matrix" values="0 0 0 0 0.2  0 0 0 0 0.2  0 0 0 0 0.2  0 0 0 0.16 0" result="n"/>'
        f'<feComposite in="n" in2="SourceGraphic" operator="in" result="n2"/>'
        f'<feBlend in="n2" in2="SourceGraphic" mode="multiply"/></filter></defs>'
        f'<g filter="url(#grain)">{rect(0, 0, W, H, sky)}{body}</g></svg>\n'
    )
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = P
    S = []

    # Music
    S.append(("music-1", "Lawn stage at dusk", p["dusk"],
              circle(230, 230, 86, p["yellow"]) + rect(0, 360, W, H - 360, p["grass"])
              + rect(520, 300, 300, 80, p["ink"]) + posts([540, 800], 160, 300, 12, p["ink"])
              + rect(520, 150, 300, 30, p["coral"]) + bulbs(546, 806, 190, 9, p["yellow"]), 1))
    S.append(("music-2", "Bandstand with bunting", p["sky"],
              rect(0, 420, W, H - 420, p["grass"]) + poly([(300, 260), (600, 260), (450, 130)], p["coral"])
              + posts([310, 440, 580], 260, 440, 14, p["white"]) + rect(300, 380, 300, 14, p["white"])
              + rect(280, 440, 340, 24, p["tan"])
              + "".join(poly([(x, 100), (x + 36, 100), (x + 18, 136)], [p["coral"], p["yellow"], p["sea"]][i % 3]) for i, x in enumerate(range(60, 880, 54))), 2))
    S.append(("music-3", "String lights over the pier at night", p["night"],
              circle(720, 120, 54, p["yellow"]) + rect(0, 380, W, H - 380, p["seadark"])
              + rect(80, 400, 740, 36, p["tan"]) + posts([110, 300, 500, 700], 300, 500, 14, p["brown"])
              + bulbs(116, 706, 300, 11, p["yellow"], 34), 3))

    # Arts
    S.append(("arts-1", "Gallery wall", p["paper"],
              rect(0, 520, W, H - 520, p["slate"])
              + rect(90, 150, 200, 240, p["ink"]) + rect(102, 162, 176, 216, p["sea"]) + circle(190, 270, 56, p["yellow"])
              + rect(350, 190, 200, 160, p["ink"]) + rect(362, 202, 176, 136, p["coral"]) + poly([(380, 330), (470, 220), (530, 330)], p["yellow"])
              + rect(610, 120, 200, 270, p["ink"]) + rect(622, 132, 176, 246, p["yellow"]) + rect(660, 200, 100, 120, p["lilac"])
              + rect(330, 470, 240, 20, p["brown"]) + posts([350, 540], 490, 540, 12, p["brown"]), 4))
    S.append(("arts-2", "Easel by the water", p["sky"],
              rect(0, 330, W, 150, p["sea"]) + rect(0, 480, W, H - 480, p["sand"])
              + path("M330 600 L430 200 L530 600 M372 420 L488 420", p["ink"], 10)
              + rect(360, 230, 160, 190, p["white"]) + rect(360, 300, 160, 50, p["sea"]) + rect(360, 350, 160, 30, p["sand"])
              + circle(610, 585, 24, p["coral"]) + circle(660, 590, 20, p["yellow"]), 5))
    S.append(("arts-3", "Mural with ladder", p["sea"],
              circle(560, 260, 150, p["yellow"]) + poly([(120, 500), (320, 180), (420, 500)], p["coral"])
              + rect(0, 520, W, H - 520, p["slate"])
              + path("M680 540 L760 120 M740 540 L820 120 M700 440 L780 440 M712 360 L792 360 M724 280 L804 280 M736 200 L816 200", p["ink"], 8)
              + rect(600, 480, 60, 50, p["tangerine"]), 6))

    # Outdoors
    S.append(("outdoors-1", "Woodland trail", p["cream"],
              rect(0, 420, W, H - 420, p["brown"]) + poly([(380, 640), (520, 640), (470, 420), (430, 420)], p["tan"])
              + trees([20, 120, 230, 330, 560, 660, 770], 440, 260, p["grassdark"])
              + trees([70, 290, 610, 720], 470, 180, p["grass"]), 7))
    S.append(("outdoors-2", "Shore at sunset", p["dusk"],
              circle(680, 220, 70, p["coral"]) + poly([(0, 300), (260, 250), (520, 300)], p["grassdark"])
              + rect(0, 300, W, 160, p["sea"]) + rect(0, 460, W, H - 460, p["sand"]), 8))
    S.append(("outdoors-3", "Kayak on the bay", p["sky"],
              poly([(0, 280), (300, 180), (620, 260), (W, 220), (W, 300), (0, 300)], p["grass"])
              + rect(0, 300, W, H - 300, p["sea"])
              + poly([(220, 430), (680, 430), (620, 480), (280, 480)], p["yellow"])
              + path("M470 320 L450 440 M380 360 L560 400", p["ink"], 8) + circle(452, 320, 18, p["coral"]), 9))

    # Family
    S.append(("family-1", "Kite on the beach", p["sky"],
              rect(0, 460, W, H - 460, p["sand"]) + rect(0, 400, W, 60, p["sea"])
              + poly([(560, 110), (700, 250), (560, 420), (420, 250)], p["yellow"])
              + path("M560 110 L560 420 M420 250 L700 250 M560 420 Q500 480 540 540 Q580 600 520 620 L220 580", p["ink"], 6)
              + poly([(530, 470), (560, 490), (530, 510)], p["coral"]) + poly([(545, 540), (575, 560), (545, 580)], p["sea"]), 10))
    S.append(("family-2", "Tall ship", p["sky"],
              rect(0, 420, W, H - 420, p["sea"])
              + poly([(200, 420), (720, 420), (660, 500), (260, 500)], p["coral"])
              + posts([360, 540], 120, 420, 12, p["ink"])
              + poly([(372, 150), (520, 300), (372, 300)], p["white"]) + poly([(552, 130), (700, 300), (552, 300)], p["white"])
              + poly([(348, 170), (220, 300), (348, 300)], p["white"]) + poly([(360, 110), (420, 130), (360, 150)], p["yellow"]), 11))
    S.append(("family-3", "Playground swing", p["sky"],
              rect(0, 460, W, H - 460, p["grass"])
              + path("M160 460 L260 140 L360 460 M540 460 L640 140 L740 460 M260 140 L640 140", p["ink"], 12)
              + line(400, 150, 400, 360, p["ink"]) + line(500, 150, 500, 360, p["ink"]) + rect(380, 360, 140, 22, p["coral"])
              + circle(780, 560, 44, p["yellow"]) + circle(100, 580, 30, p["sea"]), 12))

    # Library
    S.append(("library-1", "Bookshelves", p["cream"],
              rect(80, 60, 740, 24, p["brown"]) + rect(80, 300, 740, 24, p["brown"]) + rect(80, 540, 740, 24, p["brown"])
              + "".join(rect(100 + i * 58, 100 + (i % 3) * 18, 44, 200 - (i % 3) * 18, [p["lilac"], p["sea"], p["coral"], p["yellow"], p["lilacdark"]][i % 5]) for i in range(12))
              + "".join(rect(100 + i * 58, 340 + (i % 2) * 22, 44, 200 - (i % 2) * 22, [p["yellow"], p["lilac"], p["grass"], p["coral"], p["sea"]][i % 5]) for i in range(12)), 13))
    S.append(("library-2", "Reading chair and lamp", p["cream"],
              rect(0, 520, W, H - 520, p["slate"])
              + rect(220, 300, 300, 220, p["lilac"]) + rect(190, 260, 70, 260, p["lilacdark"]) + rect(480, 260, 70, 260, p["lilacdark"]) + rect(220, 200, 300, 110, p["lilacdark"])
              + line(700, 520, 700, 240, p["ink"], 8) + poly([(620, 240), (780, 240), (740, 160), (660, 160)], p["yellow"])
              + rect(70, 470, 90, 20, p["coral"]) + rect(60, 490, 110, 30, p["sea"]), 14))
    S.append(("library-3", "Library building", p["lilac"],
              rect(0, 520, W, H - 520, p["grass"]) + rect(150, 230, 600, 290, p["white"]) + poly([(120, 230), (780, 230), (450, 110)], p["slatedark"])
              + posts([200, 300, 400, 560, 660], 250, 520, 36, p["slate"]) + rect(430, 380, 90, 140, p["brown"])
              + rect(100, 520, 700, 20, p["slate"]) + rect(60, 540, 780, 20, p["slate"]), 15))

    # Markets
    S.append(("markets-1", "Striped awning", p["cream"],
              rect(0, 360, W, H - 360, p["sand"])
              + "".join(rect(i * 75, 120, 75, 180, p["coral"] if i % 2 == 0 else p["paper"]) for i in range(12))
              + "".join(circle(37 + i * 75, 300, 38, p["coral"] if i % 2 == 0 else p["paper"]) for i in range(12))
              + posts([100, 790], 300, 520, 14, p["ink"]) + rect(150, 380, 600, 90, p["brown"])
              + "".join(circle(200 + i * 70, 365, 24, [p["tangerine"], p["grass"], p["coral"]][i % 3]) for i in range(8)), 16))
    S.append(("markets-2", "Crates of fruit", p["cream"],
              rect(0, 500, W, H - 500, p["sand"])
              + rect(120, 330, 300, 170, p["brown"]) + rect(480, 330, 300, 170, p["tan"]) + rect(300, 160, 300, 170, p["brown"])
              + "".join(circle(160 + i * 60, 320, 30, p["tangerine"]) for i in range(5))
              + "".join(circle(520 + i * 60, 320, 30, p["coral"]) for i in range(5))
              + "".join(circle(340 + i * 60, 150, 30, p["grass"]) for i in range(5)), 17))
    S.append(("markets-3", "Farm stand with pumpkins", p["sky"],
              rect(0, 440, W, H - 440, p["grass"])
              + poly([(200, 240), (700, 240), (650, 150), (250, 150)], p["tangdark"]) + posts([230, 660], 240, 440, 14, p["brown"]) + rect(200, 360, 500, 80, p["tan"])
              + "".join(circle(260 + i * 100, 330, 40, p["tangerine"]) for i in range(5)) + "".join(rect(254 + i * 100, 280, 12, 20, p["grassdark"]) for i in range(5))
              + circle(790, 560, 50, p["tangerine"]) + circle(90, 580, 40, p["tangerine"]), 18))

    # Civic
    S.append(("civic-1", "Town hall", p["sky"],
              rect(0, 500, W, H - 500, p["grass"]) + rect(180, 240, 540, 260, p["slate"]) + poly([(150, 240), (750, 240), (450, 120)], p["ink"])
              + posts([230, 330, 530, 630], 260, 500, 30, p["white"]) + rect(410, 380, 80, 120, p["brown"])
              + line(800, 500, 800, 160, p["ink"], 8) + poly([(804, 160), (880, 190), (804, 220)], p["coral"]), 19))
    S.append(("civic-2", "Meeting hall", p["cream"],
              rect(0, 480, W, H - 480, p["slate"]) + rect(360, 100, 180, 140, p["sky"]) + rect(360, 100, 180, 140, "none")
              + rect(300, 280, 300, 24, p["brown"]) + posts([320, 570], 304, 400, 12, p["brown"])
              + "".join(rect(140 + i * 110, 400 + (i % 2) * 6, 70, 60, p["slatedark"]) for i in range(7))
              + "".join(rect(140 + i * 110, 440, 70, 10, p["ink"]) for i in range(7))
              + rect(700, 180, 60, 120, p["lilac"]), 20))
    S.append(("civic-3", "Town green gazebo", p["sky"],
              rect(0, 440, W, H - 440, p["grass"]) + poly([(300, 300), (600, 300), (450, 190)], p["slatedark"])
              + posts([320, 440, 570], 300, 440, 14, p["white"]) + rect(300, 400, 300, 12, p["white"]) + rect(280, 440, 340, 20, p["slate"])
              + line(760, 440, 760, 140, p["ink"], 8) + poly([(764, 140), (840, 170), (764, 200)], p["coral"])
              + trees([60, 140], 440, 200, p["grassdark"]), 21))

    # General, for series with no category yet
    S.append(("general-1", "Harbor with a red boat", p["cream"],
              rect(0, 280, W, H - 280, p["seadark"]) + posts([120, 170, 220, 270, 320], 230, 420, 16, p["brown"])
              + poly([(480, 330), (820, 330), (780, 400), (520, 400)], p["coral"]) + posts([490, 640], 200, 330, 10, p["ink"]), 22))
    S.append(("general-2", "Field with planting rows", p["cream"],
              poly([(0, 330), (300, 230), (620, 300), (W, 250), (W, 340), (0, 340)], p["grassdark"]) + rect(0, 330, W, H - 330, p["grass"])
              + "".join(line(0, y, W, y + 18, p["grassdark"], 6) for y in (380, 440, 500, 560)), 23))
    S.append(("general-3", "Lighthouse", p["sky"],
              rect(0, 420, W, H - 420, p["sea"]) + poly([(380, 420), (520, 420), (500, 140), (400, 140)], p["white"])
              + poly([(392, 300), (508, 300), (505, 240), (395, 240)], p["coral"]) + rect(390, 100, 120, 40, p["ink"]) + circle(450, 118, 14, p["yellow"])
              + poly([(300, 420), (600, 420), (560, 380), (340, 380)], p["slate"]), 24))

    for name, label, sky, body, seed in S:
        scene(name, label, sky, body, seed)
    print(f"wrote {len(S)} scenes to {OUT}")


if __name__ == "__main__":
    main()
