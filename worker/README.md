# The admin service

A Cloudflare Worker on `www.slack-tide.org/admin/api/*`. The admin page at `/admin/` calls it to save decisions, tracker rows and approvers and to start the pipeline; the Worker makes the GitHub commits with one token kept as a Worker secret, so approvers never see a token.

## How a request is checked

Cloudflare Access fronts `/admin/*`, so by the time a request reaches the Worker the visitor has signed in with an email code and Access has added a signed JWT in the `Cf-Access-Jwt-Assertion` header. The Worker verifies that token on every request: RS256 signature against the team's published keys at `https://slack-tide.cloudflareaccess.com/cdn-cgi/access/certs`, audience equal to `ACCESS_AUD`, issuer equal to the team, expiry. Anything short of that is a 401. The email in the token is the name recorded on every decision and in every commit message. Cross-origin requests are refused and no CORS headers are sent; the page and the Worker share the hostname, so plain `fetch("/admin/api/...", { credentials: "include" })` is all the page needs.

## Endpoints

| Method and path | Body | Does |
|---|---|---|
| `GET /admin/api/whoami` | | Returns the signed-in email |
| `POST /admin/api/decisions` | `{ decisions: [{ id, status, title, venue, edits }] }` | Appends to `approvals.yaml`; `status` is `approved` or `rejected`. `edits` is optional: the approver's overrides of what the pipeline read, any of `title`, `venue`, `town`, `description`, `cost`, `url` (strings, with length limits) and `categories` (a list from the pipeline's seven, `config.CATEGORIES`, the first one primary). The Worker checks shape and length and refuses an unknown field, the pipeline checks the names. Approving a live series again with edits is how a published listing is edited; the entry replaces the last one for the id, so it carries every override in force. The older single `category` string is still accepted as a one-item list |
| `POST /admin/api/tracker` | `{ edits: { "<row>": { "<Column>": "<value>" } } }` | Rewrites those rows of `docs/sources-tracker.csv`; row 0 is the first data row |
| `POST /admin/api/approvers` | `{ name, email, role }` | Appends to `approvers.yaml`; `role` is `approver` or `admin` |
| `DELETE /admin/api/approvers` | `{ email }` | Removes that entry from `approvers.yaml` |
| `POST /admin/api/run` | | `workflow_dispatch` of `ingest.yml` on `main` |

Every file write is a read, transform, write on `main` through the GitHub contents API, retried once on a 409 when someone else committed in between. Errors come back as `{ "error": "..." }` with the status.

The Worker does not edit the Access policy. A new approver still has to be added to the Approvers policy in the Zero Trust dashboard by hand; the page says so after a save.

## Configuration

| Name | Where | What |
|---|---|---|
| `ACCESS_TEAM` | `wrangler.toml` `[vars]` | Zero Trust team name, `slack-tide` |
| `ACCESS_AUD` | `wrangler.toml` `[vars]` | AUD tag of the "Slack-Tide Admin" application |
| `GITHUB_REPO` | `wrangler.toml` `[vars]` | `cmandle/Slack-Tide` |
| `INGEST_WORKFLOW` | `wrangler.toml` `[vars]` | `ingest.yml` |
| `GITHUB_TOKEN` | Worker secret | Fine-grained personal access token for the repository only: Contents read and write, Actions read and write |
| `CLOUDFLARE_API_TOKEN` | GitHub repository secret | Lets the deploy workflow run `wrangler deploy` (template "Edit Cloudflare Workers") |

## Deploying

`.github/workflows/deploy-worker.yml` runs `wrangler deploy` on every push to `main` that touches this folder. By hand, from this folder, with Node 20 or later:

```
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
npx wrangler deploy
```

The route in `wrangler.toml` is created by the deploy when the API token may edit routes on the zone. If it is not, add it in the dashboard: Workers & Pages, slack-tide-admin, Settings, Domains & Routes, Add, Route, `www.slack-tide.org/admin/api/*` on zone `slack-tide.org`.

## Tests

`npm test` (or `node --test test/`) runs offline checks of the JWT verification, with a key generated on the spot, and of the file transforms. No dependencies.

## Checking it is up

Signed in on the live site, open `https://www.slack-tide.org/admin/api/whoami`: it answers with your email. Without the Access cookie it answers 401, and from a browser on another origin 403.
