# Slack Tide: design brief for the site

Revision B, 18 October 2026. This supersedes the look of `preview/` (cream, sage, Plus Jakarta Sans); keep `preview/` online until `site/` replaces it, then delete it.

The design is developed on the canvas "Slack Tide design proposals" in the Claude Project "Coco's Project", row 4. Two artboards, a 390 px phone screen and a 1280 px desktop page, both showing the Events section. Their sources are committed under `design/canvas/`, flattened reference pages under `design/reference/`, tokens in `design/tokens.css`, the card illustration set under `design/art/`. When the canvas changes, the package is reissued on a `design/*` branch; the branch is the handoff, the canvas is the source.

Mood boards: analog and retro details with flat primary colours. The direct reference is a children's bookshop site (Fumayo): cream paper with a light blue square grid, thin red margin lines down both sides, a yellow wordmark block, monospace metadata, flat two-colour stickers, thick black device frame with rounded corners.

## Structure

Three sections, equal in the navigation: **Events**, **Community groups & meetups**, **Volunteer opportunities**. They are tabs. Events is the landing section. Calendar and Map are views of Events, reached from controls inside the section, not top-level navigation. Groups is a directory; Volunteer is a mixed list of dated and ongoing opportunities. Only the Events section is designed so far.

Phase 1 scope on every page: listings, filters, the provenance line, the report link, the organiser call to action. No accounts, no going or saved markers, no calendar subscription, no ratings, no comments.

## Page frame

- Canvas behind the frame: `--st-canvas`. The frame is `--st-paper` with a 2 px ink border, rounded 20 px (phone) or 24 px (desktop), max width 1200 px on desktop, 8 px in from the viewport on the phone. The frame holds everything including the footer.
- A 1 px light blue square grid (`--st-grid`) at 28 px covers the whole inside of the frame. 28 px is also the vertical leading for lists.
- Two vertical margin lines (`--st-margin`) run the full height of the frame, 20 px in from each edge on the phone and 48 px on desktop. They are drawn in front of everything: they cross the wordmark block and the search button. Implementation: a background gradient for the lines plus a positioned overlay with `pointer-events: none` so the lines paint above content.
- The design preview strip above the frame is for mockups only; the production site has no banner.

## Header

- The wordmark is the words "Slack Tide" alone, Archivo 900, on a yellow block with no outline. The block's left edge registers on the left margin line; its top edge sits against the frame border, below the rounded corner. No mark or icon beside the words.
- The header's bottom edge is a 2 px rule in `--st-rule`, drawn in front of the header content, full frame width.
- Phone header: wordmark block left, a 44 px square search button (1 px ink outline) at right, set 12 px inboard of the right margin line.
- Desktop header is 81 px tall and holds the wordmark block and the three section tabs. Search and the organiser call to action are not in the desktop header (removed in review); see Open items.

## Section tabs

- Rounded tops only (10 px phone, 12 px desktop), 1.5 px outline in `--st-rule`, square bottoms that sit on the blue rule. All three tabs have their bottoms on the rule.
- Active tab: `--st-green` fill, no bottom border. Inactive: `--st-paper` fill. Ink text, Archivo 700.
- On the phone the tabs sit in their own row under the header, on a second 2 px blue rule that spans margin line to margin line.

## Controls (Events section)

Seven tappable elements above the first listing on the phone; nothing else.

- **Town**: a native `<select>` styled as a 44 px (phone) or 40 px (desktop) square field, 1 px ink outline, mono 12 px, custom chevron. Options: All towns, then the fourteen towns from the pipeline configuration (New Bedford, Fall River, Dartmouth, Westport, Fairhaven, Acushnet, Mattapoisett, Marion, Rochester, Wareham, Somerset, Swansea, Tiverton, Little Compton). Read the list from configuration, never hardcode it in templates.
- **Map**: 1 px outlined button with a pin icon and the word, paper fill. On the phone it sits beside the town select. On desktop, **Calendar** and **Map** are two identical outlined buttons at the right of the control row. Neither carries colour: fill denotes selection, and these are links to views.
- **Category tiles**: All plus the seven categories, each a 66 px square tile with a 1 px ink outline, a 28 px two-colour icon and a mono 9 px uppercase label. Four columns on the phone (two rows), one row on desktop. The selected tile (All by default) has a yellow fill. Icons are in `design/reference/icons/`: splat (All), note, palette, tree, kite, open book, tomato, town hall. They are original drawings; fill is the category colour, outlines are ink at 1.4 px.
- Calendar on the phone is reached through the "See the whole month" link under the week-ahead list.

## Listings

**Tonight cards.** Two across on the phone, four across on desktop, 1 px ink outline, square. Cells top to bottom, divided by 1 px ink rules:

1. Title cell, Archivo 700, minimum height 34 px (40 desktop).
2. Image cell with a vertical category label block at its right, 26 px wide (34 desktop), filled in the category colour, mono uppercase, `writing-mode: vertical-rl`. The image is 76 px tall (120 desktop).
3. Date and price strip, yellow fill, mono: "SAT 7:00 PM" left, price or "Free" right.
4. Place line, mono.
5. Provenance line, mono 8 px (9 desktop) uppercase at 75% opacity: "Posted by the venue", "Read by a person", "Verified organizer". Cancelled and rescheduled states use the same slot.

On desktop a "Tonight" badge sits top-left on the image for same-day events: paper fill, 1.5 px ink outline, mono uppercase.

**The week ahead.** A grid of cards, two across on desktop (`minmax(420px, 1fr)`) and one across on the phone, 16 px column gap and 14 px row gap on desktop, 10 px on the phone. The canvas sources are `design/canvas/Week-A-*.dc.html`; the flattened pages are `design/reference/week-desktop.html` and `week-phone.html`, with screenshots. Each card is a 1 px ink outline, square, minimum height 96 px (84 on the phone), three parts left to right:

1. Date cell, 104 px wide (76 on the phone), yellow fill, no border on its right edge: day in Archivo 700 15 px (13) as "MON 26", time in mono 11 px (10) beneath, both centred.
2. Body, 12 px by 14 px padding (9 by 10): title in Archivo 700 15 px (14) on one line with ellipsis, place in mono 11 px (10), then a single outlined town chip in mono 10 px (9) uppercase, 1 px ink border, no fill.
3. Category band, 28 px wide (24), filled in the category colour, no border on its left edge, mono 10 px (9) uppercase label running vertically and reading bottom to top (`writing-mode: vertical-rl` plus `transform: rotate(180deg)`). Same device as the Tonight card's category block; note the Tonight block reads top to bottom.

Heading "The week ahead" with the date range at the right is mono uppercase with a 2 px ink underline, as before, and "See the whole month" follows the grid. Cards replace the earlier transparent rows on the ruling; the 28 px rhythm no longer governs this list. Listings are ordered by start time across the week; no day grouping, and the date repeats on every card. Decided 25 October 2026 from option 5A on the canvas.

**Images.** Every card carries a picture; the image cell is never an empty colour block. Two kinds, treated differently so they read as different things:

- An organiser photograph, when the record has one: greyscale, contrast 1.2, `mix-blend-mode: multiply` over a block of the category colour, with a 4 px radial dot screen at 30% multiplied on top (the `.ht` rules in the reference pages). Full colour is reserved for the event page. `design/reference/assets/harbor.jpg` is the stand-in for this case.
- Otherwise a stock illustration from `design/art/`, shown exactly as drawn, no halftone, no tint (the `.ill` rules). Twenty-four flat-shape scenes in the Fumayo palette with a grain filter inside each SVG: three per category family (`music`, `arts`, `outdoors`, `family`, `library`, `markets`, `civic`) plus three `general` scenes for records with no category. Choose by family, then pick one of the three from a stable hash of the series id, so the same series always shows the same scene and neighbouring cards vary. The scenes are generated by `design/tools/make_art.py`; add scenes there, never by hand-editing the SVGs.

## Tide panel

A 1 px outlined panel in the hero, paper fill: the tide staff on the left (a ruled gauge with blue water fill and a coral marker line at the current level), readings on the right in mono uppercase: height and trend ("3.8 FT ↑", "rising" on desktop), next high and low with times, and a source line.

Data: NOAA CO-OPS tide predictions for a station configured per town (default Fall River entrance, a PORTS station; confirm station IDs at implementation from the CO-OPS station lookup). Show predicted height now, direction, next high and low. Cache predictions for the day; the pipeline can fetch them in the scheduled run and write them beside `events.json`. If the data is missing or stale, show the staff unfilled with "Tide data unavailable" and no numbers. The staff is also the only brand mark; it does not appear beside the wordmark.

## Organiser call to action and footer

Phone: "Add your event" as a full-width 48 px yellow block with ink text and no outline, below the week-ahead list. Footer: two mono lines, "Every listing is read by a person before it lands here." and "Spotted something wrong? Let us know" (link).

Desktop: footer inside the frame above a 2 px blue rule, with the provenance sentence, the town list and the report link. The organiser call to action has no home on the desktop page yet (Open items).

## Type

- Archivo 700 and 900 for the wordmark, headings, tab labels, card and row titles, buttons.
- IBM Plex Mono 400 and 500 for dates, times, places, prices, labels, controls, section headings, footer.
- Both from Google Fonts. Load with `display=swap`. Uppercase is applied with CSS `text-transform` on mono labels; source copy stays sentence case per the repository convention.
- Sizes are in `design/tokens.css`.

## Colour

All text is ink `#1A1A1A` on every fill; no white text anywhere. Contrast of ink on the four Fumayo fills is above 6:1. Fills and their jobs are in `design/tokens.css`. Category colours are also the swatch and tint colours for images.

## Line weights and corners

- 2 px: outer frame (ink), header and footer rules (blue), week-ahead heading underline (ink).
- 1.5 px: tab outlines (blue), margin lines on the phone, swatch outlines.
- 1 px: all controls, all cards and their internal dividers (the week card's date cell and category band have no inner edge).
- Rounded: frame corners and tab tops only. Everything else is square. No rotation, no dashed rules, no drop shadows.

## Copy

Public copy is American English (harbor, organizer, canceled). Sentence case in source; CSS handles uppercase. No em dashes. Event titles in reference pages are placeholders; venue names are real.

## Open items

- Organiser call to action on the desktop page: footer link, or a tab-row element. Decide before `site/` is generated.
- Event page, Calendar view and Map view are not yet designed in this direction. Carry the event page's provenance line and report link from `preview/event.html`.
- Groups and Volunteer sections: layouts to follow once the Events section is signed off.
- Mascot: none. Illustration is the card scene set in `design/art/`; a character, if one ever comes, is a separate decision.
- Splat stickers in the hero are decoration; keep at most three, and drop them on narrow phones if they collide with the tide panel.

## Regenerating the reference pages

```
python3 design/tools/flatten.py design/canvas/Revision-Phone.dc.html design/reference/phone.html
python3 design/tools/flatten.py design/canvas/Revision-Desktop.dc.html design/reference/desktop.html
```

Needs python3 and node. Screenshots in `design/reference/` were rendered from those pages with headless Chromium at 2x. `python3 design/tools/make_art.py` regenerates `design/art/`.
