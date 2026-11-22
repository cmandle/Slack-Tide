/* Offline checks of the admin service: the Access JWT verification with a key made on the spot,
   the file transforms, and the request handling with GitHub and the certs endpoint faked.
   Run with `node --test test/` from worker/ (Node 20 or later). */
import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { verifyAccessJwt, appendDecisions, applyTrackerEdits, addApprover, removeApprover,
                 validateDecisions, validateTrackerEdits, validateApprover, HttpError } from "../src/index.js";

const AUD = "030ca921a895eca1f4822f5e775e579e7d9182f2ba1a488289218e6338aa5d0f";
const ISS = "https://slack-tide.cloudflareaccess.com";

function b64url(bytes) {
  const bin = typeof bytes === "string" ? bytes : String.fromCharCode(...bytes);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
async function makeKey(kid) {
  const pair = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
  const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  return { kid, priv: pair.privateKey, jwk: { kid, kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", use: "sig" } };
}
async function sign(key, claims, alg = "RS256") {
  const head = b64url(JSON.stringify({ alg, kid: key.kid, typ: "JWT" }));
  const body = b64url(JSON.stringify(claims));
  const sig = await crypto.subtle.sign({ name: "RSASSA-PKCS1-v1_5" }, key.priv, new TextEncoder().encode(head + "." + body));
  return head + "." + body + "." + b64url(new Uint8Array(sig));
}
const now = Math.floor(Date.now() / 1000);
const good = (over = {}) => ({ aud: [AUD], email: "coco@example.org", iss: ISS, iat: now - 10, nbf: now - 10, exp: now + 3600, type: "app", ...over });

test("a valid Access token verifies and yields the email", async () => {
  const key = await makeKey("k1");
  const claims = await verifyAccessJwt(await sign(key, good()), { aud: AUD, issuer: ISS, getKeys: async () => [key.jwk] });
  assert.equal(claims.email, "coco@example.org");
});

test("expired, wrong audience, wrong issuer, bad signature and missing tokens are 401", async () => {
  const key = await makeKey("k1"), other = await makeKey("k1");
  const opts = { aud: AUD, issuer: ISS, getKeys: async () => [key.jwk] };
  for (const tok of [await sign(key, good({ exp: now - 5 })), await sign(key, good({ aud: ["someone-else"] })),
                     await sign(key, good({ iss: "https://evil.example" })), await sign(other, good()),
                     await sign(key, good({ email: undefined })), "", "a.b", "not.a.jwt"]) {
    await assert.rejects(verifyAccessJwt(tok, opts), (e) => e instanceof HttpError && e.status === 401);
  }
});

test("an unknown key id triggers one refetch of the keys, and alg none is refused", async () => {
  const key = await makeKey("k2");
  let calls = [];
  const getKeys = async (force) => { calls.push(force); return force ? [key.jwk] : []; };
  const claims = await verifyAccessJwt(await sign(key, good()), { aud: AUD, issuer: ISS, getKeys });
  assert.equal(claims.email, "coco@example.org");
  assert.deepEqual(calls, [false, true]);
  await assert.rejects(verifyAccessJwt(await sign(key, good(), "none"), { aud: AUD, issuer: ISS, getKeys }), (e) => e.status === 401);
});

test("decisions append as JSON-quoted YAML entries and a missing file gets a header", () => {
  const out = appendDecisions("", [{ id: "abc", status: "approved", title: 'Say "hi": a show', venue: "The Z" },
                                   { id: "def", status: "rejected", title: "Plain" }], "luke@example.org", "2026-11-22");
  assert.ok(out.startsWith("# Approval decisions."));
  assert.ok(out.includes('- id: "abc"\n  status: approved\n  by: "luke@example.org"\n  date: "2026-11-22"\n  title: "Say \\"hi\\": a show"\n  venue: "The Z"\n'));
  assert.ok(out.includes('- id: "def"\n  status: rejected\n') && out.endsWith("\n"));
  assert.equal(appendDecisions("x: 1", [{ id: "a", status: "approved", title: "t" }], "me", "2026-01-01").slice(0, 5), "x: 1\n");
  /* A corrected category rides on the entry; an empty one writes no category line (the classifier is back in charge). */
  const fixed = appendDecisions("", [{ id: "abc", status: "approved", title: "t", category: "Arts" }, { id: "def", status: "approved", title: "t", category: "" }], "me", "2026-11-22");
  assert.ok(fixed.includes('- id: "abc"\n  status: approved\n  by: "me"\n  date: "2026-11-22"\n  title: "t"\n  category: "Arts"\n'));
  assert.ok(fixed.includes('- id: "def"\n  status: approved\n  by: "me"\n  date: "2026-11-22"\n  title: "t"\n') && fixed.split("category:").length === 2);
});

test("tracker edits rewrite the named cells and keep CSV quoting", () => {
  const csv = 'Town,Organisation,Notes\nNew Bedford,The Z,"old, note"\nWestport,Brewing,\n';
  const out = applyTrackerEdits(csv, { "1": { Notes: 'new "quoted", note', Nope: "ignored" }, "9": { Town: "x" } });
  assert.equal(out, 'Town,Organisation,Notes\nNew Bedford,The Z,"old, note"\nWestport,Brewing,"new ""quoted"", note"\n');
});

test("approvers append and remove by email", () => {
  const base = "# Who can approve.\n- name: Luke\n  email: mail@l3l.us\n  role: admin\n  added: \"2026-10-26\"\n";
  const added = addApprover(base, { name: "Coco", email: "coco@example.org", role: "approver" }, "2026-11-22");
  assert.ok(added.endsWith('- name: "Coco"\n  email: "coco@example.org"\n  role: approver\n  added: "2026-11-22"\n'));
  assert.equal(removeApprover(added, "coco@example.org"), base);
  assert.equal(removeApprover(added, "nobody@example.org"), added);
});

test("input validation refuses what the page would never send", () => {
  assert.throws(() => validateDecisions({ decisions: [] }), (e) => e.status === 400);
  assert.throws(() => validateDecisions({ decisions: [{ id: "a", status: "maybe" }] }), (e) => e.status === 400);
  assert.throws(() => validateDecisions({ decisions: [{ id: "a\nb", status: "approved" }] }), (e) => e.status === 400);
  assert.deepEqual(validateDecisions({ decisions: [{ id: " a ", status: "approved", title: "t" }] }), [{ id: "a", status: "approved", title: "t", venue: "", category: "" }]);
  assert.equal(validateDecisions({ decisions: [{ id: "a", status: "approved", title: "t", category: "Nightlife" }] })[0].category, "Nightlife");
  assert.equal(validateDecisions({ decisions: [{ id: "a", status: "approved", title: "t", category: "" }] })[0].category, "");
  assert.throws(() => validateDecisions({ decisions: [{ id: "a", status: "approved", title: "t", category: "Arts\n- id: x" }] }), (e) => e.status === 400);
  assert.throws(() => validateDecisions({ decisions: [{ id: "a", status: "approved", title: "t", category: 7 }] }), (e) => e.status === 400);
  assert.throws(() => validateTrackerEdits({ edits: { x: { A: "b" } } }), (e) => e.status === 400);
  assert.throws(() => validateTrackerEdits({ edits: { "1": { A: 5 } } }), (e) => e.status === 400);
  assert.deepEqual(validateTrackerEdits({ edits: { "1": { A: "b" } } }), { "1": { A: "b" } });
  assert.throws(() => validateApprover({ name: "x", email: "nope", role: "admin" }), (e) => e.status === 400);
  assert.throws(() => validateApprover({ name: "x", email: "a@b.co", role: "boss" }), (e) => e.status === 400);
  assert.deepEqual(validateApprover({ name: " Coco ", email: "Coco@Example.org", role: "approver" }), { name: "Coco", email: "coco@example.org", role: "approver" });
});

/* The whole handler with fetch faked: the certs endpoint and the GitHub contents API. */
test("end to end: a decision becomes a commit on approvals.yaml under the token's email", async () => {
  const key = await makeKey("k3");
  const files = { "approvals.yaml": "# Approval decisions.\n" };
  const commits = [];
  let conflictOnce = true;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    if (url === `${ISS}/cdn-cgi/access/certs`) return new Response(JSON.stringify({ keys: [key.jwk] }), { status: 200 });
    const m = url.match(/^https:\/\/api\.github\.com\/repos\/cmandle\/Slack-Tide\/contents\/([^?]+)/);
    if (m && (!init.method || init.method === "GET")) {
      const t = files[m[1]];
      if (t === undefined) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify({ sha: "sha-" + t.length, content: btoa(unescape(encodeURIComponent(t))) }), { status: 200 });
    }
    if (m && init.method === "PUT") {
      assert.equal(init.headers.Authorization, "Bearer ghp_test");
      const body = JSON.parse(init.body);
      if (conflictOnce) { conflictOnce = false; return new Response("{}", { status: 409 }); }
      files[m[1]] = decodeURIComponent(escape(atob(body.content)));
      commits.push(body.message);
      return new Response(JSON.stringify({ commit: { sha: "abc123" } }), { status: 201 });
    }
    if (url.endsWith("/actions/workflows/ingest.yml/dispatches")) { commits.push("dispatch"); return new Response(null, { status: 204 }); }
    throw new Error("unexpected fetch " + url);
  };
  try {
    const env = { ACCESS_TEAM: "slack-tide", ACCESS_AUD: AUD, GITHUB_REPO: "cmandle/Slack-Tide", INGEST_WORKFLOW: "ingest.yml", GITHUB_TOKEN: "ghp_test" };
    const jwt = await sign(key, good());
    const req = (path, init = {}) => new Request("https://www.slack-tide.org/admin/api/" + path,
      { ...init, headers: { "Cf-Access-Jwt-Assertion": jwt, "Content-Type": "application/json", ...(init.headers || {}) } });

    let r = await worker.fetch(req("whoami"), env);
    assert.equal(r.status, 200); assert.deepEqual(await r.json(), { email: "coco@example.org" });

    r = await worker.fetch(req("decisions", { method: "POST", body: JSON.stringify({ decisions: [{ id: "abc", status: "approved", title: "T" }] }) }), env);
    assert.equal(r.status, 200);
    const out = await r.json();
    assert.equal(out.saved, 1); assert.equal(out.by, "coco@example.org"); assert.equal(out.commit, "abc123");
    assert.ok(files["approvals.yaml"].includes('  by: "coco@example.org"\n'));
    assert.deepEqual(commits, ["Review: 1 decision by coco@example.org"]);   /* the 409 was retried once */

    r = await worker.fetch(req("run", { method: "POST" }), env);
    assert.equal(r.status, 200); assert.equal(commits[1], "dispatch");

    /* no token, cross-origin, and an unknown path */
    r = await worker.fetch(new Request("https://www.slack-tide.org/admin/api/whoami"), env);
    assert.equal(r.status, 401);
    r = await worker.fetch(req("whoami", { headers: { Origin: "https://evil.example" } }), env);
    assert.equal(r.status, 403);
    r = await worker.fetch(req("nothing"), env);
    assert.equal(r.status, 404);
    r = await worker.fetch(req("decisions", { method: "POST", body: "{" }), env);
    assert.equal(r.status, 400);
  } finally { globalThis.fetch = realFetch; }
});
