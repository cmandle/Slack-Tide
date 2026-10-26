# Slack Tide: working notes for Claude Code

Read this first. It is the handover from the planning sessions in the Claude app (Cowork), September to October 2026.

## What this is

A community events platform for the South Coast of Massachusetts and the Sakonnet shore of Rhode Island, run as a nonprofit. The data is the product: events are gathered from the public calendars that towns, libraries, land trusts, venues and organisations already publish, normalised, collapsed into series, classified into our own taxonomy, and published as a static site. A person approves what goes live. No ratings, no comments, no SMS.

Owner: the nonprofit's GitHub account `cmandle`. Collaborator: `loucommando` (Luke). Domain: slack-tide.org, registered and parked at ICDSoft, hosting account to be set up under the nonprofit.

## Where things are

- `pipeline/` Python 3.11+ package `slacktide`. Entry point `slacktide run`; also `build`, `pending`, `approve`, `reject`, `apply`, `digest`. Tests: `cd pipeline && pytest` (39 offline tests, fixtures shaped like real responses).
- `pipeline/slacktide/sources.yaml` the source registry. Add sources here, never in code. `role: check` sources are used for reconciliation only and never published. `kind: html` sources carry their CSS selectors in the entry (see `connectors/html.py`).
- `docs/SOURCES.md` the source inventory and outreach plan (25 October 2026): what we read, what we decided against, every candidate in the fifteen towns with the platform found and the route to it. `docs/sources-candidates.csv` is the probe list and `pipeline/tools/probe_sources.py` reruns the probe.
- `approvals.yaml` the approver's decisions, one entry per series id, appended by the admin page's Queue tab (`/admin/`; `/review/` redirects there) or by `slacktide approve` and `slacktide reject`. The last entry for an id wins. The site build publishes only approved series.
- `approvers.yaml` who can approve, with roles and dates; the admin page's People tab reads and appends to it. The gate itself is the Cloudflare Access policy, which must carry the same addresses.
- `docs/sources-tracker.csv` the outreach tracker the admin page's Sources tab edits; `pipeline/tools/tracker_xlsx.py` regenerates the spreadsheet from it.
- `data/` pipeline output, committed by the scheduled workflow: `events.json` (every series with its approval state), `pending.json` (the review queue), `run-report.json`, `tide.json`.
- `preview/` four design mockups (Discover, Calendar, Map, Event). Served at `/preview/` on GitHub Pages with a noindex tag and a banner. These are not the site, and their look is superseded by `design/`.
- `design/` the current design direction. Read `design/DESIGN.md` before any work on `site/` templates or CSS. `tokens.css` holds the values, `reference/` the flattened pages and screenshots, `art/` the card illustration set (three scenes per category family plus three general; the card image whenever a series has no photo), `canvas/` the artboard sources from the design canvas, `tools/flatten.py` regenerates `reference/` from `canvas/` and `tools/make_art.py` regenerates `art/`.
- `site/` the generated static site, written by `slacktide build` from `data/`. The ingest workflow rebuilds it on every run, so approvals reach the site without a developer. `/admin/` is the approvers' page behind Cloudflare Access (Queue, Sources, Runs, People; noindex), `/add/` the public submission form.
- `.github/workflows/ingest.yml` runs tests, the pipeline and the site build twice daily and commits `data/` and `site/`. `review.yml` opens the Sunday review issue. `pages.yml` deploys `preview/` and `site/`.

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
9. No paid scraping services (decided 2026-10-25; replaces the Diffbot and Firecrawl plan). Venues with no feed are read by the `html` connector when their events page is server-rendered HTML. Venues that draw events in the browser, or through a booking widget (the Buzzards Bay Coalition uses FareHarbor), get a conversation asking for a feed, not a headless browser.
10. Community aggregators are check sources, never published (decided 2026-10-25, extending decision 3 to Viva Fall River). Venues and organisations are ingested directly from their own sites. Measured before the flip: Viva Fall River supplied 103 of 185 series and 19 of the 20 weekend-gate series, so Fall River coverage falls until its venues (Fall River Public Library via WhoFi, Narrows Center, Canned Heat, Primo, Once Upon a Bookstore) have direct connectors. The check role's "missed" list is that to-do list.
11. Collection is daily, approval is weekly (decided 2026-10-25). The ingest workflow keeps running twice a day; the approver reviews once a week, Sunday evening, from the queue at `/review/`. The unit of approval is the series: new dates on an approved series publish without a decision, a changed title or venue makes a new series id and comes back to the queue, and rejected series stay rejected. A source may carry `review: auto` in `sources.yaml` to publish without review once it has earned trust; none does yet. Series starting within seven days sit at the top of the queue. Every decision is a line in `approvals.yaml` with a name and a date.
12. The submission API is parked (2026-10-25). Until Phase 2, organisers use the form at `/add/`, which posts to a Google Form when one is configured on the `submissions` source and falls back to email otherwise; the `sheet` connector reads the linked spreadsheet into the review queue. The message shape designed for the API is the form's field list, so the endpoint, when it comes, opens onto the same queue.

## Verified sources (live fetches, 2026-09-20 and 2026-10-11)

WordPress Events Calendar REST (`/wp-json/tribe/events/v1/events`): explorenewbedford.org (1,020 future events, check role), brownell-libraryri.org, dnrt.org, vivafallriver.com (check role since 2026-10-25), buzzardsbrew.com. Buzzards Bay Brewing leaks ~3,400 bytes of PHP warnings before the JSON body; `tribe.parse_json` skips to the first brace. ahanewbedford.org has the plugin installed but only three 2022 test events in it; the AHA Night programme is published as pages.

Server-rendered HTML (the `html` connector): zeiterion.org/events, a Webflow listing of 51 upcoming events with weekday, month, day and time in plain markup, two-date shows included (probed 2026-10-25). savebuzzardsbay.org is Craft CMS with no feed; its Bay Adventures dates live in a FareHarbor booking widget, so only the signature events are readable. ciscokitchenbar.com (BentoBox) describes weekly specials in prose with no dates.

CivicPlus iCal (`/common/modules/iCalendar/iCalendar.aspx?catID={cat}&feed=calendar`): Tiverton (cats 14, 24), Dartmouth (14, 24), Somerset (14, 23). Acushnet, Freetown, Mattapoisett, Marion and Wareham run CivicPlus too and are expected to work with discovered catIDs.

WhoFi powers six libraries (Fall River, Dartmouth, Somerset, Swansea, Mattapoisett, Rochester, Wareham). No connector yet; ask WhoFi for an export or scrape.

RSS: newbedfordlight.org/feed/ and fallriverreporter.com/feed/ are live but carry articles, not events. Stored for a later extraction pass.

Ruled out: Bandsintown (no open API, aggregation prohibited), Gannett papers (RSS switched off 2023, bot-blocked), City of New Bedford site (bot-detection challenge, needs a human relationship), Brave Search and Exa (terms prohibit storing results), Google Custom Search JSON API (closed to new customers).

## Next steps, in order

Steps 1 and 2 were completed on 2026-10-11: first live run, fixes, push, Pages, and a manual `ingest.yml` run that committed `data/`. From here the to-do list lives in GitHub Issues under the milestone "Phase 1: data spine" at https://github.com/cmandle/Slack-Tide/milestone/1, one issue per item below plus the findings from the first live run. Check there before starting work; update the issue, not this list. Labels: source, pipeline, site, ops, taxonomy, quick win.

1. Done. First live run: `cd pipeline && pip install -e ".[dev]" && pytest && slacktide run`.
2. Done. Push to `cmandle/Slack-Tide`, enable GitHub Pages with source "GitHub Actions", trigger `ingest.yml` by hand once.
3. Add the remaining CivicPlus towns and test the two untested Tribe endpoints in `sources.yaml` (`enabled: false`).
4. WhoFi connector.
5. Generate `site/` from `data/events.json`, matching `design/DESIGN.md` and `design/tokens.css` (Revision B, 18 October 2026: paper and grid, Archivo and IBM Plex Mono, Fumayo palette, three section tabs). The palette and type named for `preview/` no longer apply. The approval step (a person approves what goes live) must be designed first; it has its own issue.
6. Haiku batch classifier replacing the rule classifier.
7. Was Diffbot and Firecrawl; dropped by decision 9. Sources with no feed go through the `html` connector (Zeiterion first, 2026-10-25) or a request to the venue for a feed.
8. Direct Fall River connectors to replace what the Viva Fall River check source used to supply (decision 10).
9. Configure the Google Form behind `/add/` and the published sheet behind the `submissions` source (decision 12).

Measured on the first live run, 2026-10-11: 527 rows from eight sources, 156 series across seven towns; weekend gate 8 series across 3 towns against the target of 50 across 5; the 56 series Explore New Bedford has that we lack are the New Bedford venue connectors to build next.

## Conventions

Sentence case in all copy. No em dashes. Venue names are real South Coast organisations; event titles in mockups are placeholders. Every published record carries `source_id`. Never ingest Facebook or Instagram. Keep the pipeline runnable on a volunteer's laptop with `pip install -e .` and nothing else.

## GitHub, accounts and setup

**Accounts.** The repository `cmandle/Slack-Tide` is owned by the nonprofit's GitHub account `cmandle`. Luke's personal account `loucommando` is a collaborator with push access. Commit as whichever account is signed in on the machine; do not create or sign in to accounts on anyone's behalf. Automated commits from the scheduled workflow use the identity set in `ingest.yml` (`slack-tide-bot`, `bot@slack-tide.org`), which is a label on commits, not a real account.

**First push.** The folder `C:\Dev\slack-tide` is not yet a git repository. Run `git init -b main`, `git add -A`, commit, `git remote add origin https://github.com/cmandle/Slack-Tide.git`, `git push -u origin main`. Git for Windows prompts for a browser sign-in the first time. Default branch is `main`.

**Repository visibility.** Keep it public. GitHub Pages and Actions minutes are free on public repositories; the data is public events, and the code has no secrets in it. If it is ever made private, Pages and Actions become paid features.

**GitHub Pages.** Source is "GitHub Actions"; `pages.yml` deploys `site/` and `preview/`, and the ingest workflow starts it after each run (a push made with the workflow's own token never triggers another workflow). The site is live at `https://www.slack-tide.org/` with the custom domain `www.slack-tide.org` and Enforce HTTPS on; the domain was verified under the `cmandle` account on 2026-10-26.

**DNS and Cloudflare (since 2026-10-26).** DNS for slack-tide.org is served by Cloudflare (`dom.ns.cloudflare.com`, `eva.ns.cloudflare.com`) on the Free plan; the registration stays at ICDSoft. Records: four proxied A records on the apex to GitHub Pages, proxied CNAME `www` to `cmandle.github.io`, Cloudflare Email Routing's MX and SPF, the DKIM and DMARC records, and the GitHub verification TXT. Cloudflare settings: SSL mode Full, Always Use HTTPS, a redirect rule apex to www, a cache rule bypassing `/admin/` and `/review/`. Email: `hello@slack-tide.org` is forwarded by Cloudflare Email Routing to a mailbox the maintainer reads; receive-only. The login gate: Cloudflare Access (Zero Trust team `slack-tide`) fronts `/admin/*` and `/review/*` on www and the apex, one-time PIN by email, an Allow policy listing the approvers' addresses; the list lives in the Cloudflare dashboard, not in the repository. The runbook with every setting is `docs/CLOUDFLARE-ACCESS.md`. The Cloudflare account is under the maintainer's l3l.us address until the nonprofit has its own; ownership can be transferred.

**Workflow files.** `.github/workflows/ingest.yml` and `pages.yml` could not be written by the Cowork session (protected path) and were delivered as downloads. Confirm both exist before the first push. `ingest.yml` needs `contents: write`, which it declares, and the repository's Actions settings must allow workflows to write (Settings, Actions, General, Workflow permissions: "Read and write permissions"). Trigger `ingest.yml` manually from the Actions tab once to confirm it runs on GitHub's machines, not only locally.

**Secrets.** None are needed for Phase 1. When the Haiku classifier arrives, its key goes in Settings, Secrets and variables, Actions, as `ANTHROPIC_API_KEY`, read by the workflow as `${{ secrets.NAME }}`. The review page needs no secret in the repository: the approver pastes a fine-grained personal access token (this repository only, Contents read and write, Actions read and write) into the page once, and it stays in that browser. Locally they go in `pipeline/.env`, which `.gitignore` already excludes. Never put a key in a file that is committed.

**ICDSoft.** Holds the domain registration (expires 2027-09-20, auto-renewal was off on 2026-10-26). The domain is parked on the maintainer's l3l.us hosting account there, which is harmless but means ICDSoft's MySQL and mailboxes belong to a personal account; a hosting account under the nonprofit is still the plan if Phase 2 uses ICDSoft's MySQL rather than Supabase. DNS and email no longer go through ICDSoft (see Cloudflare above).

**Windows specifics.** Use PowerShell or Git Bash. Virtual environment activation is `.venv\Scripts\activate` in PowerShell; if it is refused, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. If Git Bash is missing, Claude Code falls back to PowerShell for its shell tool, which works but some commands in this file are written for Bash.

**People.** Approvers, as of 2026-10-26: Luke (mail@l3l.us) and Coco (cmandle015@gmail.com). Both are on the Cloudflare Access policy for `/admin/` and `/review/`. The approver, not the developer, decides what publishes. Adding an approver means adding their email to that policy in the Cloudflare dashboard (Zero Trust, Access controls, Applications, Slack-Tide Admin, the Approvers policy); the admin page will do this through the Phase B Worker once it exists.

**Do not.** Ingest Facebook, Instagram, Meetup or Nextdoor. Store or republish results from Brave Search or Exa. Pay for a scraping service. Commit anything from `data/` or `site/` by hand; the workflow owns those folders. Rebuild the design in a framework. Treat Explore New Bedford or Viva Fall River as a source of record.
