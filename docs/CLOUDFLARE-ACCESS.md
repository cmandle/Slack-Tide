# Putting Cloudflare in front of slack-tide.org, and Access in front of /admin/

Written and carried out 26 October 2026: the zone, Email Routing and the Access gate are live, verified from the outside. Phase B (section 7) remains. The goal: the admin page and the review queue open only for people on a short list, who sign in with a one-time code sent to their email. No token to paste, nothing to remember. Cloudflare's free plan does all of it; the only change on our side is where the domain's DNS is served from.

How it works: Cloudflare takes over DNS for slack-tide.org and proxies the website (GitHub Pages stays the host). Cloudflare Access, part of Zero Trust, then intercepts every request to `/admin/*` and `/review/*` and shows a login page unless the visitor has signed in with an allowed email address. Everything else on the site stays public and unchanged.

Every step below is yours to do in a browser; none of it is code. Expect about forty minutes plus a wait for DNS to move. Do it on a weekday morning, not a Sunday evening, so a hiccup does not land on review night.

## 0. What the zone holds today

Looked up on 26 October 2026. DNS is served by ICDSoft (`ns1.server272.com`, `ns2.server272.com`).

| Record | Name | Value | Keep |
|---|---|---|---|
| A | slack-tide.org | 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153 | Yes, proxied |
| CNAME | www | cmandle.github.io | Yes, proxied |
| MX | slack-tide.org | mail.slack-tide.org, priority 0 | Yes, DNS only |
| TXT | slack-tide.org | `v=spf1 a mx include:server272.smtp-spf.sureserver.com ~all` | Yes |
| TXT | _dmarc | `v=DMARC1; p=none;` | Yes |
| TXT | dkim._domainkey | `v=DKIM1; k=rsa; p=MIGf...` (the long key; copy it whole) | Yes |
| A | mail | none; the MX points at a name with no address | See the note |

The DMARC and DKIM rows come from the ICDSoft panel on 26 October; public resolvers did not return them, so check them in the Cloudflare import rather than trusting a lookup.

Two things worth knowing before you start:

- **Email at the domain is not live.** The MX record points at `mail.slack-tide.org`, which has no address, so mail to anything at slack-tide.org bounces today. That is the ICDSoft hosting account still to be set up (CLAUDE.md). When it exists, add the `mail` A record ICDSoft gives you, in Cloudflare, as DNS only. Nothing in this runbook makes email worse; it is already off.
- **The domain is not yet verified under the `cmandle` GitHub account** (no `_github-pages-challenge-cmandle` record). Step 1 fixes that at the same time.

## 1. Before the move: verify the domain with GitHub (5 minutes)

GitHub, signed in as `cmandle`: Settings, Pages, Add a domain, enter `slack-tide.org`. GitHub shows a TXT record name (`_github-pages-challenge-cmandle.slack-tide.org`) and value. Add that TXT record at ICDSoft now, or at Cloudflare in step 2 if you prefer; verification can complete after the move. This stops anyone else's Pages site from claiming the domain.

## 2. Create the Cloudflare account and zone (10 minutes)

1. Sign up at dash.cloudflare.com under a nonprofit address that works today (not hello@slack-tide.org, see above). Turn on two-factor authentication.
2. Add a site: `slack-tide.org`, Free plan.
3. Cloudflare scans the existing records and offers to import them. Make the list match the table above:
   - the four A records on the apex, **proxied** (orange cloud);
   - `www` CNAME to `cmandle.github.io`, **proxied**;
   - MX and the SPF TXT, **DNS only** (grey cloud; mail must never be proxied);
   - the GitHub verification TXT from step 1.
4. Cloudflare shows two nameservers. For this zone they are `dom.ns.cloudflare.com` and `eva.ns.cloudflare.com` (assigned 26 October 2026).

## 3. Point the domain at Cloudflare (5 minutes, then wait)

At ICDSoft, in the domain's management page (the registration is an Enom one resold by ICDSoft, but the change is made in the ICDSoft account, not at Enom), replace `ns1.server272.com` and `ns2.server272.com` with `dom.ns.cloudflare.com` and `eva.ns.cloudflare.com`. Make sure DNSSEC is off on the same page before saving; it was not in use on 26 October. Cloudflare emails when it sees the change; usually within an hour, sometimes up to a day. Until then ICDSoft keeps answering and nothing is broken.

## 4. Settings on the zone (10 minutes)

In the Cloudflare dashboard for slack-tide.org:

- **SSL/TLS, Overview**: encryption mode **Full**. Not Flexible (it would loop with GitHub's redirect to HTTPS) and not Full (strict) yet, because GitHub's certificate check for a custom domain wants the domain to resolve straight to GitHub, which it no longer does behind the proxy. Visitors get Cloudflare's certificate either way. If GitHub's Pages settings later show the certificate as expired, that is why; the site stays secure because Cloudflare terminates HTTPS at the edge. Full (strict) can be tried once Cloudflare issues an origin certificate, which is optional.
- **SSL/TLS, Edge Certificates**: Always Use HTTPS on; Automatic HTTPS Rewrites on.
- **Rules, Redirect Rules**: one rule, apex to www. Incoming requests where hostname equals `slack-tide.org`, dynamic redirect to `concat("https://www.slack-tide.org", http.request.uri.path)`, status 301. (GitHub does this today; the rule keeps it working behind the proxy.)
- **Caching, Cache Rules**: one rule, bypass cache when the URI path starts with `/admin/` or `/review/`. The rest of the site can follow GitHub's own ten-minute cache header.
- **GitHub, repository Settings, Pages**: custom domain stays `www.slack-tide.org`. Leave Enforce HTTPS as it is.

## 4b. Email at the domain, through Cloudflare Email Routing (5 minutes)

There is no mailbox at slack-tide.org yet and no mail server behind the MX record. Cloudflare Email Routing, free, forwards mail for the domain to a mailbox you already have.

1. In the zone, Email, Email Routing: enable it. Cloudflare replaces the MX and SPF records with its own; accept that, since the ICDSoft ones deliver nothing today.
2. Destination addresses: add the mailbox that should receive the mail (the l3l address). Click the confirmation link Cloudflare sends it.
3. Routing rules: `hello@slack-tide.org` to that destination. Add a catch-all if anything at the domain should arrive there.
4. Keep the DKIM and DMARC records as they are.

Routing is receive-only. Replies go out from the receiving mailbox unless its provider allows "send as" with the hello@ address, which most do. If the ICDSoft hosting account with its own mailboxes is set up later, switch the MX back to ICDSoft's and turn routing off; nothing else changes.

## 5. Zero Trust: the login gate (10 minutes)

1. From the Cloudflare dashboard, open Zero Trust. Pick a team name when asked; it becomes the login address, `<team>.cloudflareaccess.com`. `slacktide` is fine. Free plan.
2. Settings, Authentication: the default **One-time PIN** is already on. That is the email code. No other identity provider is needed.
3. Access, Applications, Add an application, **Self-hosted**:
   - Name: Slack Tide admin
   - Session duration: 24 hours
   - Application domain: `www.slack-tide.org`, path `admin` (then Add a domain and repeat with path `review`, so both pages sit behind the same policy)
   - Policy: name "Approvers", action **Allow**, include **Emails**, list the approver's address and yours. Nothing else.
   - Leave App Launcher off. Save.
4. Access, Applications: add a second self-hosted application for `slack-tide.org` (the apex) with the same two paths, so a visitor who types the address without www is covered before the redirect rule fires. Same policy.

## 6. Check it (5 minutes)

In a private window open `https://www.slack-tide.org/admin/` (or `/review/` until the admin page exists). You should see Cloudflare's login page, enter an allowed email, get a six-digit code by email, and land on the page. Try an email not on the list: it must be refused. Open the public home page: no login.

If the login page does not appear, the record is probably not proxied (grey cloud) or the nameservers have not moved yet. Access only works on proxied hostnames.

## 7. What this changes in the repository

Nothing is required for the gate to work. The pages are already built with `noindex`. The one later improvement that Access makes possible:

Set up on 26 October 2026: team `slack-tide` (login at `slack-tide.cloudflareaccess.com`), application "Slack-Tide Admin" with AUD tag `030ca921a895eca1f4822f5e775e579e7d9182f2ba1a488289218e6338aa5d0f`, one-time PIN with instant authentication, HTTP-only and binding cookies on, SameSite Lax. Mind the identity provider dropdown: the entry called "Cloudflare" means signing in with a Cloudflare dashboard account, not the email code; the email code is "One-time PIN", which must be enabled under Settings, Authentication before it appears.

**Phase B, writes without a token (built 22 November 2026).** The admin page no longer holds a GitHub token. Its saves go to the admin service, a Cloudflare Worker in `worker/` routed on `www.slack-tide.org/admin/api/*`, behind the same Access application. On every request the Worker verifies the `Cf-Access-Jwt-Assertion` header that Access adds (RS256, keys from `https://slack-tide.cloudflareaccess.com/cdn-cgi/access/certs`, audience equal to the AUD tag above, kept as the Worker variable `ACCESS_AUD`), refuses anything else with 401, and records the token's email as the name on every decision and in every commit message. It makes the GitHub writes with one fine-grained token kept as the Worker secret `GITHUB_TOKEN`: appends to `approvals.yaml`, rewrites rows of `docs/sources-tracker.csv`, appends to or removes from `approvers.yaml`, and dispatches `ingest.yml`, each as a read-modify-write on `main` with one retry on 409. Cross-origin requests are refused. The Worker does not edit the Access policy; a new approver is still added to the Approvers policy by hand. `.github/workflows/deploy-worker.yml` deploys it on every push to `main` that touches `worker/`. Free tier is a hundred thousand requests a day, which is several lifetimes of Sunday reviews.

One-time setup, in order, all in a browser:

1. **Cloudflare API token for the deploy.** Cloudflare dashboard, My Profile, API Tokens, Create Token, template "Edit Cloudflare Workers", account resources the account, zone resources `slack-tide.org`. Copy it.
2. **GitHub repository secret.** `cmandle/Slack-Tide`, Settings, Secrets and variables, Actions, New repository secret, `CLOUDFLARE_API_TOKEN`, paste the token from step 1.
3. **First deploy.** Actions, "Deploy admin Worker", Run workflow (or merge a change under `worker/`). It runs the Worker's offline tests, then `wrangler deploy`, which creates the Worker `slack-tide-admin` and the route `www.slack-tide.org/admin/api/*`. If the run says it could not add the route, add it in Workers & Pages, slack-tide-admin, Settings, Domains & Routes, Add, Route, pattern `www.slack-tide.org/admin/api/*`, zone `slack-tide.org`.
4. **GitHub token for the Worker.** GitHub, Settings, Developer settings, Personal access tokens, Fine-grained, Generate new token: resource owner `cmandle`, repository access "Only select repositories" with `Slack-Tide`, permissions Contents read and write and Actions read and write, expiry a year. Copy it.
5. **Worker secret.** Cloudflare, Workers & Pages, slack-tide-admin, Settings, Variables and secrets, Add, type Secret, name `GITHUB_TOKEN`, paste the token from step 4, Deploy. (`ACCESS_TEAM`, `ACCESS_AUD`, `GITHUB_REPO` and `INGEST_WORKFLOW` are already there from `wrangler.toml`.)
6. **Check.** Signed in on the live site, open `https://www.slack-tide.org/admin/api/whoami`: it answers with your email. Then on `/admin/`, the strip at the top says "Signed in as ... saves are recorded under this address", and a decision saved from the Queue tab appears as a commit "Review: 1 decision by ..." on `main`.
7. **Clean up.** Approvers who pasted a token into the old page can revoke it (GitHub, Settings, Developer settings, Fine-grained tokens) and clear the page's storage; the page no longer reads it.

When the token from step 4 expires, repeat steps 4 and 5. If the Access application is ever deleted and recreated, put its new AUD tag in `worker/wrangler.toml` and redeploy.

## 8. Record it when done

Update CLAUDE.md, "GitHub, accounts and setup": DNS is at Cloudflare, nameservers named, the record list above, Access in front of `/admin/` and `/review/` with the allowed addresses kept in the Zero Trust dashboard rather than in the repository. ICDSoft keeps the registration and, once set up, the mailbox.
