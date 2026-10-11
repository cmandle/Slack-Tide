# Slack Tide: working notes for Claude Code

Read this first. It is the handover from the planning sessions in the Claude app (Cowork), September to October 2026.

## What this is

A community events platform for the South Coast of Massachusetts and the Sakonnet shore of Rhode Island, run as a nonprofit. The data is the product: events are gathered from the public calendars that towns, libraries, land trusts, venues and organisations already publish, normalised, collapsed into series, classified into our own taxonomy, and published as a static site. A person approves what goes live. No ratings, no comments, no SMS.

Owner: the nonprofit's GitHub account `cmandle`. Collaborator: `loucommando` (Luke). Domain: slack-tide.org, registered and parked at ICDSoft, hosting account to be set up under the nonprofit.

## Where things are

- `pipeline/` Python 3.11+ package `slacktide`. Entry point `slacktide run`. Tests: `cd pipeline && pytest` (21 offline tests, fixtures shaped like real responses).
- `pipeline/slacktide/sources.yaml` the source registry. Add sources here, never in code. `role: check` sources are used for reconciliation only and never published.
- `data/` pipeline output, committed by the scheduled workflow.
- `preview/` four design mockups (Discover, Calendar, Map, Event). Served at `/preview/` on GitHub Pages with a noindex tag and a banner. These are not the site.
- `site/` the generated static site, not yet built.
- `.github/workflows/ingest.yml` runs tests and the pipeline twice daily and commits `data/`. `pages.yml` deploys `preview/` and `site/`.

Companion documents live in the Claude Project "Coco's Project": the project brief (phases, decisions log, measured findings), the Phase 0 source tracker (135 researched organisations with verified feed URLs), and the design canvas.

## Architecture decisions, do not relitigate without reason

1. Phase 1 is a scheduled GitHub Action producing a static artifact, deployed as a static site. No database and no application server until Phase 2 submissions need one. ICDSoft MySQL (remote access per user) or Supabase are the candidates then.
2. Python for the pipeline, plain generated HTML and JavaScript for the site. No frontend framework.
3. Explore New Bedford (`explorenewbedford.org`) is itself an aggregator of New Bedford venues. It is a coverage CHECK against independently gathered results, not a source of record. Member venues are ingested directly. `reconcile.py` reports matched, missed and primary-only counts; "missed" is the connector to-do list, "primary-only" is the project's reason to exist.
4. Series collapsing is the primary data-model problem, ahead of cross-source deduplication. Measured 2026-10-11: Explore New Bedford 176 rows in 60 days, 56 distinct titles, repeat ratio 3.14; Tiverton municipal iCal 243 rows of senior-centre bingo through 2027. The calendar is unreadable without `series.py`.
5. Source categories are never trusted. Explore New Bedford's top two are "Free" and "Downtown". `normalize.classify()` is a rule classifier over our taxonomy; a Claude Haiku batch classifier is planned to replace it (about $1 a month at expected volume).
6. Municipal iCal feeds carry public holidays as events. `config.HOLIDAY_TITLES` drops them. Category IDs on CivicPlus must be discovered per town; most return empty.
7. Venue canonicalisation is fuzzy (`rapidfuzz`, threshold 92) because sources spell the same place several ways. ZIP codes appear in city fields; `config.ZIP_TO_TOWN` resolves them.
8. The Phase 1 gate: fifty DISTINCT events or series on a typical weekend across at least five towns, after holiday filtering and series collapsing. Rows are not the unit.

## Verified sources (live fetches, 2026-09-20 and 2026-10-11)

WordPress Events Calendar REST (`/wp-json/tribe/events/v1/events`): explorenewbedford.org (1,020 future events, check role), brownell-libraryri.org, dnrt.org, vivafallriver.com, buzzardsbrew.com. Buzzards Bay Brewing leaks ~3,400 bytes of PHP warnings before the JSON body; `tribe.parse_json` skips to the first brace.

CivicPlus iCal (`/common/modules/iCalendar/iCalendar.aspx?catID={cat}&feed=calendar`): Tiverton (cats 14, 24), Dartmouth (14, 24), Somerset (14, 23). Acushnet, Freetown, Mattapoisett, Marion and Wareham run CivicPlus too and are expected to work with discovered catIDs.

WhoFi powers six libraries (Fall River, Dartmouth, Somerset, Swansea, Mattapoisett, Rochester, Wareham). No connector yet; ask WhoFi for an export or scrape.

RSS: newbedfordlight.org/feed/ and fallriverreporter.com/feed/ are live but carry articles, not events. Stored for a later extraction pass.

Ruled out: Bandsintown (no open API, aggregation prohibited), Gannett papers (RSS switched off 2023, bot-blocked), City of New Bedford site (bot-detection challenge, needs a human relationship), Brave Search and Exa (terms prohibit storing results), Google Custom Search JSON API (closed to new customers).

## Next steps, in order

1. First live run: `cd pipeline && pip install -e ".[dev]" && pytest && slacktide run`. Expect the fixtures to have missed things. Fix, rerun.
2. Push to `cmandle/Slack-Tide`, enable GitHub Pages with source "GitHub Actions", trigger `ingest.yml` by hand once.
3. Add the remaining CivicPlus towns and test the two untested Tribe endpoints in `sources.yaml` (`enabled: false`).
4. WhoFi connector.
5. Generate `site/` from `data/events.json`, matching the design in `preview/`: cream `#FBF8F1`, ink `#2E2A22`, sage `#4A6B4E`, Plus Jakarta Sans, eight muted category colours.
6. Haiku batch classifier replacing the rule classifier.
7. Diffbot free tier for Tier 2 sources with no feed; Firecrawl as fallback.

## Conventions

Sentence case in all copy. No em dashes. Venue names are real South Coast organisations; event titles in mockups are placeholders. Every published record carries `source_id`. Never ingest Facebook or Instagram. Keep the pipeline runnable on a volunteer's laptop with `pip install -e .` and nothing else.

## GitHub, accounts and setup

**Accounts.** The repository `cmandle/Slack-Tide` is owned by the nonprofit's GitHub account `cmandle`. Luke's personal account `loucommando` is a collaborator with push access. Commit as whichever account is signed in on the machine; do not create or sign in to accounts on anyone's behalf. Automated commits from the scheduled workflow use the identity set in `ingest.yml` (`slack-tide-bot`, `bot@slack-tide.org`), which is a label on commits, not a real account.

**First push.** The folder `C:\Dev\slack-tide` is not yet a git repository. Run `git init -b main`, `git add -A`, commit, `git remote add origin https://github.com/cmandle/Slack-Tide.git`, `git push -u origin main`. Git for Windows prompts for a browser sign-in the first time. Default branch is `main`.

**Repository visibility.** Keep it public. GitHub Pages and Actions minutes are free on public repositories; the data is public events, and the code has no secrets in it. If it is ever made private, Pages and Actions become paid features.

**GitHub Pages.** After the first push, in the repository Settings under Pages, set Source to "GitHub Actions". `pages.yml` then deploys on every push that touches `preview/` or `site/`. The preview appears at `https://cmandle.github.io/Slack-Tide/preview/`. The custom domain `slack-tide.org` comes later, once `site/` is generated and approved; the preview is placeholder content and should not sit on the real domain. Order of operations: first verify the domain under the `cmandle` account settings (Pages, Verified domains) so no other Pages site can claim it; then at ICDSoft's DNS add a CNAME `www` to `cmandle.github.io` and four A records on the apex to 185.199.108.153, 185.199.109.153, 185.199.110.153 and 185.199.111.153; then enter the domain under the repository's Pages settings and, after the certificate is issued, tick Enforce HTTPS. Pages was enabled and the first deploy and first ingest run succeeded on 2026-10-11.

**Workflow files.** `.github/workflows/ingest.yml` and `pages.yml` could not be written by the Cowork session (protected path) and were delivered as downloads. Confirm both exist before the first push. `ingest.yml` needs `contents: write`, which it declares, and the repository's Actions settings must allow workflows to write (Settings, Actions, General, Workflow permissions: "Read and write permissions"). Trigger `ingest.yml` manually from the Actions tab once to confirm it runs on GitHub's machines, not only locally.

**Secrets.** None are needed for Phase 1. When the Haiku classifier and Diffbot connector arrive, their keys go in Settings, Secrets and variables, Actions, as `ANTHROPIC_API_KEY` and `DIFFBOT_TOKEN`, read by the workflow as `${{ secrets.NAME }}`. Locally they go in `pipeline/.env`, which `.gitignore` already excludes. Never put a key in a file that is committed.

**ICDSoft.** Holds the domain registration and will hold a hosting account under the nonprofit, separate from any personal account. Its MySQL allows remote connections per user and is the Phase 2 database candidate alongside Supabase. For Phase 1 it provides email at the domain and DNS; nothing is deployed there.

**Windows specifics.** Use PowerShell or Git Bash. Virtual environment activation is `.venv\Scripts\activate` in PowerShell; if it is refused, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. If Git Bash is missing, Claude Code falls back to PowerShell for its shell tool, which works but some commands in this file are written for Bash.

**People.** A daily approver is identified; name and contact to be added here when confirmed. The approver, not the developer, decides what publishes.

**Do not.** Ingest Facebook, Instagram, Meetup or Nextdoor. Store or republish results from Brave Search or Exa. Commit anything from `data/` by hand; the workflow owns that folder. Rebuild the design in a framework. Treat Explore New Bedford as a source of record.
