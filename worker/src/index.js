/* Slack Tide admin service: a Cloudflare Worker on www.slack-tide.org/admin/api/* that makes the
   admin page's GitHub writes so approvers never handle a token.

   Every request arrives through Cloudflare Access, which fronts /admin/* and adds the visitor's
   signed identity as the Cf-Access-Jwt-Assertion header. The Worker verifies that JWT (RS256,
   keys from the team's certs endpoint, audience ACCESS_AUD), takes the email from it, and does
   the write against the repository with the GITHUB_TOKEN secret. Nothing else is accepted.

   Endpoints (JSON in, JSON out):
     GET    /admin/api/whoami      -> { email }
     POST   /admin/api/decisions   { decisions: [{ id, status, title, venue?, category? }] } -> approvals.yaml
                                   (category: the approver's correction of the classifier, kept on every
                                   run; an empty string records the decision without one)
     POST   /admin/api/tracker     { edits: { "<row>": { "<Column>": "<value>" } } } -> docs/sources-tracker.csv
     POST   /admin/api/approvers   { name, email, role } -> approvers.yaml (append)
     DELETE /admin/api/approvers   { email } -> approvers.yaml (remove)
     POST   /admin/api/run         -> workflow_dispatch of the ingest workflow

   The file edits are the same ones admin.js made in the browser until November 2026: append
   to approvals.yaml, rewrite rows of the tracker CSV, append to or drop from approvers.yaml,
   each as a read-modify-write on main with one retry on 409. */

const PATHS = { approvals: "approvals.yaml", tracker: "docs/sources-tracker.csv", approvers: "approvers.yaml" };
const GITHUB = "https://api.github.com";
const USER_AGENT = "slack-tide-admin-worker";

/* ------------------------------------------------------------------ small helpers */

export function yamlStr(s) { return JSON.stringify(String(s)); }

function b64urlToBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function utf8FromB64(s) {
  const bin = atob(s.replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}
function b64FromUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
function today() { return new Date().toISOString().slice(0, 10); }

export class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extra },
  });
}

/* ------------------------------------------------------------------ Access JWT */

/* Verify a Cloudflare Access application token. `getKeys` returns the JWKS key list; it is called
   again once if the token's key id is not in the first answer (Cloudflare rotates keys). Returns the
   claims. Throws HttpError(401) on anything short of a valid, unexpired token for our audience. */
export async function verifyAccessJwt(token, { aud, issuer, getKeys, now = () => Date.now() / 1000 }) {
  if (!token || typeof token !== "string") throw new HttpError(401, "No Access token");
  const parts = token.split(".");
  if (parts.length !== 3) throw new HttpError(401, "Malformed Access token");
  let header, claims;
  try {
    header = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[0])));
    claims = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[1])));
  } catch (e) { throw new HttpError(401, "Malformed Access token"); }
  if (header.alg !== "RS256" || !header.kid) throw new HttpError(401, "Unsupported Access token");

  let keys = await getKeys(false);
  let jwk = keys.find((k) => k.kid === header.kid);
  if (!jwk) { keys = await getKeys(true); jwk = keys.find((k) => k.kid === header.kid); }
  if (!jwk) throw new HttpError(401, "Unknown signing key");

  const key = await crypto.subtle.importKey("jwk", { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify({ name: "RSASSA-PKCS1-v1_5" }, key, b64urlToBytes(parts[2]),
    new TextEncoder().encode(parts[0] + "." + parts[1]));
  if (!ok) throw new HttpError(401, "Access token signature does not verify");

  const t = now();
  if (typeof claims.exp !== "number" || claims.exp < t) throw new HttpError(401, "Access token has expired");
  if (typeof claims.nbf === "number" && claims.nbf > t + 60) throw new HttpError(401, "Access token not yet valid");
  const auds = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud || !auds.includes(aud)) throw new HttpError(401, "Access token is for another application");
  if (issuer && claims.iss !== issuer) throw new HttpError(401, "Access token is from another issuer");
  if (!claims.email || typeof claims.email !== "string") throw new HttpError(401, "Access token carries no email");
  return claims;
}

/* The team's public keys, cached in the isolate for an hour and refreshed on an unknown kid. */
let keyCache = { keys: null, at: 0 };
function keysFetcher(certsUrl) {
  return async (force) => {
    const fresh = keyCache.keys && Date.now() - keyCache.at < 3600_000;
    if (fresh && !force) return keyCache.keys;
    const r = await fetch(certsUrl, { cf: { cacheTtl: 3600, cacheEverything: true } });
    if (!r.ok) throw new HttpError(502, "Could not fetch the Access signing keys");
    const body = await r.json();
    keyCache = { keys: body.keys || [], at: Date.now() };
    return keyCache.keys;
  };
}

/* ------------------------------------------------------------------ file transforms */

export function appendDecisions(text, decisions, by, date) {
  const entries = decisions.map((d) => {
    const lines = [`- id: ${yamlStr(d.id)}`, `  status: ${d.status}`, `  by: ${yamlStr(by)}`, `  date: ${yamlStr(date)}`,
                   `  title: ${yamlStr(d.title || "")}`];
    if (d.venue) lines.push(`  venue: ${yamlStr(d.venue)}`);
    if (d.category) lines.push(`  category: ${yamlStr(d.category)}`);
    return lines.join("\n");
  }).join("\n") + "\n";
  if (!text) text = "# Approval decisions. One entry per series id; the last entry for an id wins.\n";
  if (text[text.length - 1] !== "\n") text += "\n";
  return text + entries;
}

/* CSV helpers: RFC 4180, quotes doubled, fields with commas, quotes or newlines quoted. */
export function parseCsv(text) {
  const rows = []; let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows;
}
export function csvField(v) { v = String(v == null ? "" : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }

/* edits: { "<row index, 0 = first data row>": { "<Column>": "<value>" } }. Unknown rows and columns are skipped. */
export function applyTrackerEdits(text, edits) {
  const rows = parseCsv(text), header = rows[0] || [];
  for (const i of Object.keys(edits)) {
    const r = rows[1 + Number(i)]; if (!r) continue;
    for (const field of Object.keys(edits[i])) { const c = header.indexOf(field); if (c >= 0) r[c] = edits[i][field]; }
  }
  return rows.map((r) => r.map(csvField).join(",")).join("\n") + "\n";
}

export function addApprover(text, { name, email, role }, date) {
  if (text && text[text.length - 1] !== "\n") text += "\n";
  return text + `- name: ${yamlStr(name)}\n  email: ${yamlStr(email)}\n  role: ${role}\n  added: ${yamlStr(date)}\n`;
}

export function removeApprover(text, email) {
  /* drop the entry whose email line matches; entries start at "- name:" */
  const blocks = text.replace(/\n+$/, "").split(/\n(?=- )/);
  const kept = blocks.filter((b) => b.indexOf("email: " + email) < 0 && b.indexOf('email: "' + email + '"') < 0);
  return kept.join("\n") + "\n";
}

/* ------------------------------------------------------------------ input validation */

const EMAIL = /^[^\s@"']+@[^\s@"']+\.[^\s@"']+$/;
const CATEGORY = /^[A-Za-z][A-Za-z &]{0,39}$/;
function str(v, max, what) {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[\r\n]/.test(v)) throw new HttpError(400, `Bad ${what}`);
  return v.trim();
}
export function validateDecisions(body) {
  const list = body && Array.isArray(body.decisions) ? body.decisions : null;
  if (!list || !list.length || list.length > 500) throw new HttpError(400, "Send between 1 and 500 decisions");
  return list.map((d) => {
    if (!d || !["approved", "rejected"].includes(d.status)) throw new HttpError(400, "Bad decision status");
    /* The category list lives in the pipeline (config.CATEGORIES) and the page's select is built
       from it; here only the shape is checked, and the pipeline drops a name it does not know. */
    if (d.category !== undefined && d.category !== "" && (typeof d.category !== "string" || !CATEGORY.test(d.category))) throw new HttpError(400, "Bad category");
    return { id: str(d.id, 120, "series id"), status: d.status, title: str(d.title || "untitled", 300, "title"),
             venue: d.venue ? str(d.venue, 300, "venue") : "", category: d.category ? d.category.trim() : "" };
  });
}
export function validateTrackerEdits(body) {
  const edits = body && body.edits && typeof body.edits === "object" ? body.edits : null;
  if (!edits || !Object.keys(edits).length) throw new HttpError(400, "No tracker edits");
  const out = {};
  for (const i of Object.keys(edits)) {
    if (!/^\d{1,5}$/.test(i) || !edits[i] || typeof edits[i] !== "object") throw new HttpError(400, "Bad tracker row");
    out[i] = {};
    for (const field of Object.keys(edits[i])) {
      if (field.length > 60) throw new HttpError(400, "Bad tracker column");
      const v = edits[i][field];
      if (typeof v !== "string" || v.length > 2000) throw new HttpError(400, "Bad tracker value");
      out[i][field] = v;
    }
  }
  return out;
}
export function validateApprover(body) {
  const name = str(body && body.name, 60, "name");
  const email = str(body && body.email, 120, "email").toLowerCase();
  if (!EMAIL.test(email)) throw new HttpError(400, "Bad email");
  const role = body.role === "admin" ? "admin" : body.role === "approver" ? "approver" : null;
  if (!role) throw new HttpError(400, "Bad role");
  return { name, email, role };
}

/* ------------------------------------------------------------------ GitHub */

function ghHeaders(env) {
  return { "Authorization": "Bearer " + env.GITHUB_TOKEN, "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT };
}

/* Read a file on main, transform its text, write it back; retries once on a 409 (someone else wrote first). */
async function putFile(env, path, transform, message, attempt = 0) {
  const base = `${GITHUB}/repos/${env.GITHUB_REPO}/contents/${path}`;
  const r = await fetch(`${base}?ref=main`, { headers: ghHeaders(env) });
  let cur = null;
  if (r.status !== 404) {
    if (!r.ok) throw new HttpError(502, `GitHub read failed: ${r.status}`);
    cur = await r.json();
  }
  const text = cur ? utf8FromB64(cur.content) : "";
  const body = { message, content: b64FromUtf8(transform(text)), branch: "main" };
  if (cur) body.sha = cur.sha;
  const w = await fetch(base, { method: "PUT", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (w.status === 409 && attempt === 0) return putFile(env, path, transform, message, 1);
  if (!w.ok) throw new HttpError(502, `GitHub write failed: ${w.status}`);
  const out = await w.json();
  return (out.commit && out.commit.sha) || "";
}

async function dispatchWorkflow(env) {
  const r = await fetch(`${GITHUB}/repos/${env.GITHUB_REPO}/actions/workflows/${env.INGEST_WORKFLOW}/dispatches`,
    { method: "POST", headers: { ...ghHeaders(env), "Content-Type": "application/json" }, body: JSON.stringify({ ref: "main" }) });
  if (r.status !== 204) throw new HttpError(502, `Could not start the pipeline: ${r.status}`);
}

/* ------------------------------------------------------------------ request handling */

/* Same origin only: the page and this Worker share the hostname, so a browser sends no Origin on a
   same-origin fetch, or one equal to the page's. Anything else is refused; no CORS headers are ever sent. */
function sameOrigin(request, url) {
  const origin = request.headers.get("Origin");
  if (origin && origin !== url.origin) return false;
  const site = request.headers.get("Sec-Fetch-Site");
  if (site && site !== "same-origin" && site !== "none") return false;
  return true;
}

async function readJson(request) {
  const ct = request.headers.get("Content-Type") || "";
  if (!ct.toLowerCase().startsWith("application/json")) throw new HttpError(415, "Send JSON");
  try { return await request.json(); } catch (e) { throw new HttpError(400, "Bad JSON"); }
}

async function route(request, env, email) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/^\/admin\/api\/?/, "").replace(/\/+$/, "");
  const m = request.method;
  const date = today();

  if (path === "whoami" && m === "GET") return json({ email });

  if (path === "decisions" && m === "POST") {
    const decisions = validateDecisions(await readJson(request));
    const n = decisions.length;
    const commit = await putFile(env, PATHS.approvals, (t) => appendDecisions(t, decisions, email, date),
      `Review: ${n} decision${n === 1 ? "" : "s"} by ${email}`);
    return json({ saved: n, by: email, commit });
  }

  if (path === "tracker" && m === "POST") {
    const edits = validateTrackerEdits(await readJson(request));
    const n = Object.keys(edits).length;
    const commit = await putFile(env, PATHS.tracker, (t) => applyTrackerEdits(t, edits),
      `Tracker: ${n} change${n === 1 ? "" : "s"} by ${email}`);
    return json({ saved: n, commit });
  }

  if (path === "approvers" && m === "POST") {
    const a = validateApprover(await readJson(request));
    const commit = await putFile(env, PATHS.approvers, (t) => addApprover(t, a, date), `Approvers: add ${a.email} (by ${email})`);
    return json({ added: a.email, date, commit });
  }

  if (path === "approvers" && m === "DELETE") {
    const body = await readJson(request);
    const target = str(body && body.email, 120, "email").toLowerCase();
    if (!EMAIL.test(target)) throw new HttpError(400, "Bad email");
    const commit = await putFile(env, PATHS.approvers, (t) => removeApprover(t, target), `Approvers: remove ${target} (by ${email})`);
    return json({ removed: target, commit });
  }

  if (path === "run" && m === "POST") {
    await dispatchWorkflow(env);
    return json({ started: true, workflow: env.INGEST_WORKFLOW, by: email });
  }

  throw new HttpError(404, "No such endpoint");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (!url.pathname.startsWith("/admin/api")) throw new HttpError(404, "Not found");
      if (!sameOrigin(request, url)) throw new HttpError(403, "Cross-origin requests are not accepted");
      if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: { "Allow": "GET, POST, DELETE" } });
      if (!env.ACCESS_AUD || !env.ACCESS_TEAM) throw new HttpError(500, "ACCESS_AUD and ACCESS_TEAM are not set");
      if (!env.GITHUB_TOKEN) throw new HttpError(500, "GITHUB_TOKEN is not set");
      const team = `https://${env.ACCESS_TEAM}.cloudflareaccess.com`;
      const claims = await verifyAccessJwt(request.headers.get("Cf-Access-Jwt-Assertion"),
        { aud: env.ACCESS_AUD, issuer: team, getKeys: keysFetcher(`${team}/cdn-cgi/access/certs`) });
      return await route(request, env, claims.email.toLowerCase());
    } catch (e) {
      const status = e instanceof HttpError ? e.status : 500;
      const message = e instanceof HttpError ? e.message : "Something went wrong in the admin service";
      if (!(e instanceof HttpError)) console.error(e && e.stack ? e.stack : e);
      return json({ error: message }, status);
    }
  },
};
