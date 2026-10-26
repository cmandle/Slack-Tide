# Source inventory and outreach plan

Compiled 25 October 2026 from the source registry, the run report, the Phase 0 findings in CLAUDE.md, and a live probe of 104 sites across the fifteen towns (`python pipeline/tools/probe_sources.py docs/sources-candidates.csv`). The registry in `pipeline/slacktide/sources.yaml` is the truth about what the pipeline reads; this document is the map around it. Keep it current by rerunning the probe when a site is redesigned, and by reading `reconcile.check_missed` in `data/run-report.json`, which lists the venues the check sources carry that we still lack.

Decisions that shape every choice below: venues and organisations are read directly, aggregators are checks only, no paid scraping, nothing from Facebook or Instagram, and a person approves what publishes (CLAUDE.md, decisions 3, 9, 10, 11).

## 1. The integration types, cheapest first

| Type | What it is | Our cost | Status |
|---|---|---|---|
| **Tribe REST** | WordPress "The Events Calendar" plugin answers at `/wp-json/tribe/events/v1/events` with clean JSON, venue and all. | A registry entry. | Built (`tribe`) |
| **CivicPlus iCal** | Municipal sites on CivicPlus publish an ICS feed per calendar category at `/common/modules/iCalendar/iCalendar.aspx?catID=N&feed=calendar`. | A registry entry plus discovering the category ids per town. | Built (`ical`) |
| **Plain iCal** | Any public ICS address: a Google Calendar's public feed, a LibCal calendar, a Squarespace or Tribe `?ical=1` twin. | A registry entry. | Built (`ical`, verify once with a non-CivicPlus feed) |
| **Squarespace JSON** | Any Squarespace events page answers `?format=json` with every item's `startDate` and `endDate` in epoch milliseconds, title, excerpt and location. | A 40-line connector, then a registry entry per site. | To build |
| **HTML listing** | A server-rendered events page read with CSS selectors declared on the registry entry. | Fifteen minutes per site to write the selectors and save a fixture; breaks on redesign and fails loudly. | Built (`html`) |
| **WhoFi** | The library calendar system behind seven of our libraries (`<town>-ma.whofi.com/calendar/full`). No documented feed. | One connector covers all seven; ask WhoFi for an export first. | To build (issue 5) |
| **LibCal** | Springshare's library calendar; each calendar has an iCal and RSS address once you know its id. | A registry entry once the library sends the id. | Plain iCal |
| **Event plugins with their own API** | Event Espresso (REST at `/wp-json/ee/...`), EventPrime, EventON. | Small per-plugin connectors, only worth it for two or more sites each. | Not yet |
| **Eventbrite** | Organisers who sell through Eventbrite have a public organiser page and an API that lists their events with a free personal token. Terms allow display with a link back. | A connector and a token in Actions secrets. | Not yet |
| **Wix Events** | Wix renders the event list into the page as JSON for its viewer; readable but undocumented and fragile. | Prefer asking the organisation for an iCal (Wix offers "Add to calendar" per event, not a feed). | Ask |
| **Ticketing systems** | ShoWare (Narrows), Salesforce (Zeiterion, NBSO), FareHarbor (Coalition, Community Boating), NeonCRM (WHALE). The venue's own site usually mirrors them. | Read the venue site; ask the venue for an export where it does not. | HTML or ask |
| **Submission form** | `/add/` on the site, posting to a Google Form the `sheet` connector reads. For organisations that only post on Facebook or by email. | Configure the form (issue 18); then it is their effort, not ours. | Built, form not yet configured |
| **Check sources** | Aggregators and media calendars, read for the coverage report and never published. | A registry entry with `role: check`. | Built |

## 2. In use today

From the run report of 25 October 2026 (`rows` is occurrences in the 60-day window before series collapsing).

| Source | Town | Type | Rows | Role | Notes |
|---|---|---|---|---|---|
| Town of Tiverton | Tiverton | CivicPlus iCal, cats 14 and 24 | 191 | primary | Cat 24 is the senior centre; venues missing on most rows (issue 10). |
| The Zeiterion | New Bedford | HTML listing (Webflow) | 30 | primary | Added 25 October; two-date shows handled. |
| Brownell Library | Little Compton | Tribe REST | 22 | primary | Feed sends no venue; the registry default fills it. |
| Town of Dartmouth | Dartmouth | CivicPlus iCal, cats 14 and 24 | 20 | primary | Mostly board and committee meetings. |
| Dartmouth Natural Resources Trust | Dartmouth | Tribe REST | 16 | primary | |
| Town of Somerset | Somerset | CivicPlus iCal, cats 14 and 23 | 5 | primary | |
| Buzzards Bay Brewing | Westport | Tribe REST | 1 | primary | PHP warnings before the JSON, tolerated; returned a 500 on 25 October. |
| Viva Fall River | Fall River | Tribe REST | 252 | check | Aggregator; its missed list is the Fall River to-do list (section 4). |
| Explore New Bedford | New Bedford | Tribe REST | 146 | check | Aggregator; 923 future events on the site. |
| Submissions | any | published Google Sheet | 0 | primary, disabled | Waiting on the form (issue 18). |
| Little Compton Historical Society | Little Compton | Tribe REST | | disabled | Plugin confirmed; the probe hit a rate limit (429), so test by hand and enable. |
| Mattapoisett Land Trust | Mattapoisett | Tribe REST | | disabled | Probe confirmed: 2 events. Enable. |
| Buzzards Bay Coalition | regional | HTML listing | | disabled | Dates live in a FareHarbor widget; see section 5. |
| The New Bedford Light | New Bedford | RSS | | disabled | Articles, not events; a later extraction pass (issue 14). |

Published towns today: Tiverton, Dartmouth, Little Compton, New Bedford, Somerset, Westport. The weekend gate needs fifty series across five towns, so the order of work below is about towns first and volume second.

## 3. Decided against

| What | Why | Instead |
|---|---|---|
| Facebook, Instagram, Meetup, Nextdoor | Terms forbid automated collection; the APIs do not expose other people's events; a personal feed is not a source of record. | The form at `/add/`; a conversation with the organisation; Facebook as a discovery tool for the approver, never an input. |
| Paid scraping (Diffbot, Firecrawl) | Decision 9. | The `html` connector, or a request for a feed. |
| Bandsintown | No open API; aggregation prohibited. | Venues directly. |
| Gannett papers (SouthCoast Today, Herald News) | RSS off since 2023; the site answers our probe with a paywall code (402). | The New Bedford Light and Fall River Reporter for later article extraction. |
| City of New Bedford site | Bot-detection challenge. | A human relationship with the city; the venues themselves. |
| Brave Search, Exa | Terms prohibit storing results. | |
| Google Custom Search JSON API | Closed to new customers. | |
| Explore New Bedford, Viva Fall River as sources of record | Aggregators: not their taxonomy, not their venue spellings, and anything nobody submitted is missing (decisions 3 and 10). | Check role; their venues directly. |
| AHA! New Bedford's calendar | The Events Calendar plugin is installed but holds three 2022 test events; the programme is prose pages. | Ask AHA to use the plugin they have (section 5). The venues carry the actual AHA Night events. |
| Cisco Kitchen & Bar's happenings page | Prose about weekly specials, no dates; the live music page is a 404. | A hand-entered series through the form, or nothing. |
| Destination New Bedford | The city tourism site renders nothing readable without JavaScript. | Explore New Bedford already covers the same ground as a check. |

## 4. Candidates, by town

Each row says what the probe found on 25 October and what we would do. "Feed" means no contact is needed. Priority reflects the gate: a new town outranks more volume in a covered town, and weekend content outranks weekday meetings.

### Fall River (no primary source today; priority 1)

The Viva Fall River check carries 103 series across 34 venues. These are the venues, in order of what they contribute.

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Narrows Center for the Arts | WordPress; ticketing on `narrowscenter.showare.com`; 19 series missed | HTML listing on the venue site (`narrowscenter.org`), falling back to the ShoWare page | High |
| Fall River Public Library | WhoFi (`fallriver-ma.whofi.com`); 14 series missed | WhoFi connector | High |
| Canned Heat Craft Beer Co. | 9 series missed; site has a certificate error | Likely Facebook-first. Ask; offer the form | High |
| Primo on Water Street | 6 series missed; domain to confirm | Ask; offer the form | Medium |
| Greater Fall River Re-CREATION | `re-creation.org`, no platform detected | Ask | Medium |
| Children's Museum of Greater Fall River | Squarespace; `/events?format=json` answers with 8 dated items | Squarespace JSON | High (feed) |
| SoCo Art Labs | Tribe installed, 0 events in it; uses Eventbrite | Eventbrite organiser, or ask them to use the plugin | Medium |
| The Tipsy Toboggan, Once Upon a Bookstore, Saint James Irish Pub, Stumpy's | Wix or no site events; 2 to 3 series each | Form | Low |
| Battleship Cove | Wix with its events viewer; 11 event titles in the page | Ask for an iCal; Wix extraction as a last resort | Medium |
| Fall River Historical Society | WordPress, `/events/` pages | HTML listing | Medium |
| Lafayette-Durfee House, Marine Museum, Fall River Little Theatre | Certificate errors or unreachable | Confirm the domains in a browser; ask | Low |
| Bristol Community College | Static page of upcoming events | HTML listing | Low |
| City of Fall River | Blocks our probe (403) | Ask the clerk's office whether the calendar has an iCal address | Medium |
| Lizzie Borden House | Blocks our probe (403) | Ask | Low |

### Westport (one series today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Westport Free Public Library | **Tribe REST answers with 1,141 future events** although the home page blocks our probe | Feed, add now | High |
| Westport Land Conservation Trust | WordPress; the programmes page has no readable headings (probably JavaScript) | Ask for a feed | Medium |
| Westport Rivers Vineyard | Squarespace; `/events-sunset-music` has no dated items in JSON | Ask | Low |
| Westport Historical Society | WordPress with `/events/` pages, RSS of 9 | HTML listing | Medium |
| Town of Westport | Blocks our probe (403) | Ask the town for the iCal address; confirm the platform in a browser | Medium |
| Westport Fair | Certificate error | Confirm the domain; a once-a-year festival, so the form may do | Low |

### Marion (no source today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Elizabeth Taber Library | **Tribe REST, 185 events**, plus an iCal twin; venue field empty, so set the registry default | Feed, add now | High |
| Town of Marion | **CivicPlus iCal, 46 events on category 14** | Feed, add now; discover the other categories | High |
| Marion Art Center | WordPress with Event Espresso (22 event blocks on the page) | Event Espresso REST, else HTML listing | Medium |
| Marion Natural History Museum | Tribe plugin present, REST answers 403 | Ask them to allow the REST endpoint, or use the `?ical=1` twin | Medium |
| Sippican Lands Trust | WordPress `/events/`, unreachable at probe time | Retry; HTML listing | Low |
| Sippican Historical Society | Blocks our probe | Ask | Low |

### Mattapoisett (no source today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Town of Mattapoisett | **CivicPlus iCal, 10 events on category 14** | Feed, add now | High |
| Mattapoisett Free Public Library | WhoFi (`mattapoisett-ma.whofi.com`) | WhoFi connector | High |
| Mattapoisett Land Trust | Tribe REST, 2 events, already in the registry disabled | Enable | High (feed) |
| The Wanderer (tri-town weekly) | **Tribe REST, 26 events**: a community calendar for Marion, Mattapoisett and Rochester | Check source for the tri-town, like Viva for Fall River | Medium |
| Mattapoisett Historical Society | Wix | Ask | Low |

### Wareham (no source today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Town of Wareham | **CivicPlus iCal, 5 events on category 14** | Feed, add now; discover the other categories | High |
| Wareham Free Library | WhoFi (`wareham-ma.whofi.com`) | WhoFi connector | High |
| YMCA Southcoast | **Tribe REST, 2 events** (Gleason, Mattapoisett branches); programmes sit in Daxko | Feed, add now | Medium |
| Wareham Land Trust | WordPress calendar page with 10 headings | HTML listing | Medium |
| Onset Bay Center | Run by the Buzzards Bay Coalition | See section 5 | |

### Rochester (no source today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Town of Rochester | **CivicPlus iCal, 12 events on category 14** | Feed, add now | High |
| Plumb Memorial Library | WhoFi (`plumb-ma.whofi.com`) | WhoFi connector | High |
| Rochester Land Trust | WordPress, no event pages found | Ask | Low |

### Freetown and Acushnet (no source today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Town of Freetown | **CivicPlus iCal, 71 events on category 14** | Feed, add now; expect meetings, filter closures | High |
| Town of Acushnet | **CivicPlus iCal, 6 events on category 14** | Feed, add now | High |
| Russell Memorial Library (Acushnet), James White Memorial Library (Freetown) | Domains did not resolve | Confirm the addresses; both are SAILS libraries and may be WhoFi | Medium |
| Acushnet Sawmill | Run by the Buzzards Bay Coalition | See section 5 | |

### Fairhaven and Swansea (no source today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Millicent Library (Fairhaven) | Drupal 10 with an events calendar view | Ask for the iCal address (Drupal calendars usually have one); else HTML listing | High |
| Swansea Free Public Library | WhoFi (`swanseafree-ma.whofi.com`) | WhoFi connector | High |
| Towns of Fairhaven and Swansea | Both block our probe (403) | Ask the clerk's office for the calendar's iCal address | Medium |
| Fairhaven Historical Society | Wix | Ask | Low |

### Somerset (two series today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Somerset Public Library | Wix site with the WhoFi calendar embedded | WhoFi connector | High |

### Dartmouth (28 series today)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Dartmouth Public Libraries | WhoFi per the handover; the domain we tried did not resolve | Confirm the address; WhoFi connector | High |
| Lloyd Center for the Environment | WordPress calendar with 8 event pages | HTML listing | High (weekend outdoor content) |
| Round the Bend Farm | WordPress `/events/` | HTML listing | Medium |
| The Trustees of Reservations | WordPress `/events/` across the state | HTML listing filtered to Westport Town Farm, Cornell Farm, Copicut Woods, Lyman Reserve, East Over | Medium |
| Mass Audubon (Allens Pond) | Own programme system | Ask for an export | Medium |
| UMass Dartmouth | Calendar looks like Localist, which has public iCal and JSON | Confirm; plain iCal | Medium |
| Dartmouth Cultural Center | Domain did not resolve | Confirm | Low |

### Tiverton (33 series today, all from the town)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Tiverton Public Library | LibCal (`tivertonlibrary.libcal.com`) | Ask the library for the calendar id, then plain iCal | High |
| Four Corners Arts Center | Squarespace; the concerts page is not an events collection (no dated JSON) | Ask them to use a Squarespace events page, else HTML | Medium |
| Sakonnet Preservation Association | WordPress; programmes on Eventbrite | Eventbrite organiser | Medium |
| Tiverton Land Trust | Squarespace, no dated items in JSON | Ask | Low |
| Sandywoods Center for the Arts | Domain did not resolve | Confirm; a music venue worth having | Medium |
| Tiverton Historical Society | Certificate error | Confirm | Low |

### Little Compton (13 series today, from Brownell)

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Little Compton Historical Society | Tribe plugin, probe rate-limited | Enable the existing registry entry after one manual check | High (feed) |
| Sakonnet Vineyard | Squarespace; `/events?format=json` answers with 12 dated items (live music, trivia) | Squarespace JSON | High (feed, weekend content) |
| Little Compton Community Center | Domain did not resolve | Confirm | Medium |
| Town of Little Compton | Blocks our probe | Ask | Low |
| Sakonnet Times (East Bay Media) | Webflow calendar page | Check source candidate for the Sakonnet shore, once read | Low |

### New Bedford (24 series today, all Zeiterion)

The Explore New Bedford check lists what we miss; these are the venues behind it.

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| New Bedford Whaling Museum | WordPress; programmes are a `program` post type exposed at `/wp-json/wp/v2/program` (no date field in the standard output); 11 series missed | HTML listing on `/programs/`, or ask whether the date is in a meta field we can request | High |
| New Bedford Art Museum | WordPress `/events/` with 17 headings; 8 series missed | HTML listing | High |
| New Bedford Free Public Library | Joomla with a Google Calendar embed on the home page | Ask for the public calendar id, then plain iCal | High |
| Gallery X | WordPress with EventPrime (32 event links) | HTML listing | Medium |
| Hatch Street Studios | Squarespace; `/events?format=json` answers with 5 dated items | Squarespace JSON | High (feed) |
| New Bedford Symphony Orchestra | WordPress; tickets through the Zeiterion's Salesforce | Already arrives through the Zeiterion listing | Done |
| New Bedford Historical Society | WordPress, imports from Eventbrite | Eventbrite organiser, or HTML | Medium |
| New Bedford Fishing Heritage Center | WordPress `/calendar/` | HTML listing | Medium |
| Groundwork Southcoast | WordPress `/events/` | HTML listing | Low |
| WHALE | Events in a NeonCRM portal | HTML on the portal, or ask | Low |
| Community Boating Center | FareHarbor | Ask for an export | Low |
| Buttonwood Park Zoo | WordPress, no event pages found on the home page | Find the events page; HTML | Medium |
| Rotch-Jones-Duff House | WordPress; Hamlet runs there (24 rows in the check) | Find the events page; HTML | Medium |
| The Vault, Greasy Luck, Co-Creative Center | Domains did not resolve or 404 | Confirm; these are the bar and open-mic venues the check shows | Medium |
| Moby Dick Brewing, Kilburn Mill, Your Theatre, Feast of the Blessed Sacrament | WordPress; Feast runs EventON | HTML; the Feast is one weekend a year, so the form may do | Low |
| Seamen's Bethel, Whaling National Historical Park | NPS has a free API with park events | NPS API (key in secrets) | Low |
| New Bedford Guide | WordPress media site with an events category | Check source candidate | Low |

### Regional

| Organisation | Probe | Route | Priority |
|---|---|---|---|
| Buzzards Bay Coalition | Craft CMS; Bay Adventures dates in FareHarbor | Ask (issue 19) | High: covers Westport, Dartmouth, Acushnet, Wareham |
| One SouthCoast Chamber | WordPress; events likely in GrowthZone, which has iCal | Ask for the iCal address | Low (business events) |
| South Coast Media Group (Dartmouth Week, Sippican Week, Westport Shorelines) | Drupal calendar with many entries | Check source candidate for Dartmouth, Westport, the tri-town | Medium |
| SouthCoast Artists | Squarespace, no events collection | Form for the open studio tour | Low |

## 5. Outreach plan

**Who writes.** Email from hello@slack-tide.org, signed by a named person at the nonprofit. Libraries answer to their director; towns to the clerk's office or IT; museums and venues to whoever runs communications or the box office.

**What we send.** One page, "How to get your events on Slack Tide", with three doors: you probably already have a feed (how to find it on WordPress, CivicPlus, Squarespace, Google Calendar, LibCal, WhoFi); you can send us an iCal or CSV export; or you can use the form at slack-tide.org/add. Every message says what we are, that listings are free, that a person reads each one, and that we link back to them. Nothing asks for a login or a token.

**The ask by type.**
- Feed exists (section 1, rows marked "add now"): no contact needed. Add, run, and send a courtesy note once they are live so they can check their listings.
- Platform has a feed we cannot see (LibCal, Google Calendar, Drupal, GrowthZone, Localist): one email asking for the address.
- Plugin present but switched off or empty (AHA, SoCo Art Labs, Marion Natural History Museum): one email saying the plugin they have would make their events appear everywhere, including with us.
- Booking widget or ticketing only (Coalition, Community Boating, Mass Audubon, Battleship Cove): ask for a weekly or monthly export; offer to read a Google Calendar if they keep one.
- No site or Facebook only (the Fall River bars, Canned Heat, Primo): a short note with the form link. Expect that most will not use it until someone they know does, so start with the ones the check source shows are active.
- Blocked town sites (Fall River, Westport, Fairhaven, Swansea, Little Compton): confirm the platform in a browser first; CivicPlus towns have the iCal path whether or not the home page likes robots.

**Order.** Four waves, one every two weeks, tracked as one GitHub issue per wave with a checklist, label `source`.

1. *Feeds in hand* (no contact): Westport library, Elizabeth Taber Library, the six CivicPlus towns, Mattapoisett Land Trust, Little Compton Historical, YMCA Southcoast, The Wanderer as a check; the Squarespace connector for Hatch Street, the Children's Museum and Sakonnet Vineyard. This wave alone adds Marion, Mattapoisett, Wareham, Rochester, Freetown and Acushnet to the published towns.
2. *Build and read* (no contact): the WhoFi connector for seven libraries, then HTML entries for the Narrows, the Whaling Museum, the Art Museum, the Lloyd Center, Gallery X, Wareham Land Trust and Westport Historical Society.
3. *One-email asks*: NBFPL and Tiverton library (calendar ids), Millicent Library, the Coalition, AHA, Marion Natural History Museum, SoCo Art Labs, the blocked towns, UMass Dartmouth, the Chamber.
4. *Relationships*: the Fall River venues without feeds, Battleship Cove, Mass Audubon, the New Bedford bars once their domains are confirmed, Sandywoods, the historical societies on Wix.

**Measuring.** After each wave, the run report answers three things: towns with published series (the gate wants five), the weekend series count (the gate wants fifty), and the check sources' missed lists, which should shrink. Record the numbers in the wave's issue when it closes.

## 6. Open questions

- Whether WhoFi will provide an export, which decides whether wave 2 is a connector or a conversation.
- Whether the Explore New Bedford and Viva Fall River checks should also seed the venue list automatically: a `check_missed` entry with a venue we have no registry entry for is a candidate row for `docs/sources-candidates.csv`.
- The tri-town: The Wanderer as a check gives the same coverage measure for Marion, Mattapoisett and Rochester that the two city aggregators give for the cities.
- Domains marked "did not resolve" above are guesses that missed; a few minutes in a browser fixes each one, and the candidates file should be corrected as they are found.
