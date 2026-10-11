# Slack Tide

A community events platform for the South Coast of Massachusetts and the Sakonnet shore of Rhode Island, run as a nonprofit.

Slack tide is the still water at the turn of the tide. The platform gathers events from the public calendars that towns, libraries, land trusts, venues and organisations already publish, normalises them into one shape, collapses weekly series so the calendar is readable, and publishes the result as a static site. A person approves what goes live.

## Layout

| Path | What it is |
|---|---|
| `pipeline/` | Python ingestion pipeline: connectors, normalisation, series collapsing, export |
| `pipeline/slacktide/sources.yaml` | The registry of sources the pipeline reads. Add a source here, not in code |
| `data/` | The pipeline's output. `events.json` is committed by the scheduled run |
| `site/` | Generated static site (Phase 1) |
| `preview/` | Design mockups, served at `/preview/` on GitHub Pages |
| `.github/workflows/` | Scheduled ingestion and Pages deployment |

## Running the pipeline

```bash
cd pipeline
python -m venv .venv && source .venv/bin/activate
pip install -e .
slacktide run            # fetch every enabled source, normalise, export data/events.json
slacktide reconcile      # compare the aggregate against Explore New Bedford
slacktide report         # print counts by town, source and category
pytest                   # offline tests against recorded fixtures
```

## Principles

The event data is the product. Series are collapsed, holidays are filtered, venues are canonicalised, and every record carries the source it came from. Explore New Bedford is used as a coverage check against independently gathered results, never as the source of record.

## Status

Phase 1, data spine. See the project brief for the phase plan and the source tracker for the 135 researched organisations.
