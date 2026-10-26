/* Slack Tide admin page. Four tabs over server-rendered markup. Who is signed in comes from
   Cloudflare Access, which fronts /admin/; every save goes to the repository through the GitHub
   contents API with a token kept in this browser, until the admin service takes that over.
   Writes: approvals.yaml (append), docs/sources-tracker.csv (rewrite rows), approvers.yaml
   (append or remove), and a workflow dispatch for the pipeline. */
(function () {
  "use strict";
  var main = document.querySelector("main.admin");
  if (!main) return;
  var repo = main.getAttribute("data-repo");
  var api = "https://api.github.com/repos/" + repo;
  var paths = { approvals: main.getAttribute("data-approvals"), tracker: main.getAttribute("data-tracker"),
                approvers: main.getAttribute("data-approvers") };
  var workflow = main.getAttribute("data-workflow");
  var KEY_TOKEN = "st.admin.token";
  var who = "";   /* the signed-in email, from Access */

  function store(k, v) { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch (e) {} }
  function read(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } }
  function statusIn(section, msg, bad) {
    var el = section.querySelector("[data-status]");
    if (el) { el.textContent = msg; el.classList.toggle("is-bad", !!bad); }
  }

  /* ---- tabs: the hash picks the section */
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".adm-tab"));
  var sections = Array.prototype.slice.call(document.querySelectorAll(".adm-section"));
  function showTab(id) {
    if (!document.getElementById(id)) id = "queue";
    sections.forEach(function (s) { s.hidden = s.id !== id; });
    tabs.forEach(function (t) { if (t.getAttribute("href") === "#" + id) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current"); });
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function (e) { e.preventDefault(); var id = t.getAttribute("href").slice(1); history.replaceState(null, "", "#" + id); showTab(id); });
  });
  showTab((location.hash || "#queue").slice(1));

  /* ---- who is signed in: Cloudflare Access answers on the protected hostname */
  var whoEl = document.getElementById("who");
  fetch("/cdn-cgi/access/get-identity", { credentials: "include" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (id) {
      if (id && id.email) { who = id.email; whoEl.innerHTML = ""; whoEl.appendChild(document.createTextNode("Signed in as ")); var b = document.createElement("b"); b.textContent = who; whoEl.appendChild(b); whoEl.appendChild(document.createTextNode(" through Cloudflare Access · ")); var a = document.createElement("a"); a.href = "/cdn-cgi/access/logout"; a.textContent = "sign out"; whoEl.appendChild(a); }
      else { whoEl.textContent = "Not behind the login gate (a local build, or the gate is off). Decisions are recorded under the name you give."; }
    })
    .catch(function () { whoEl.textContent = "Not behind the login gate. Decisions are recorded under the name you give."; });

  /* ---- token setup */
  var tokenEl = document.getElementById("rev-token"), setup = document.getElementById("setup");
  tokenEl.value = read(KEY_TOKEN);
  if (!tokenEl.value) setup.open = true;
  document.getElementById("rev-save-setup").addEventListener("click", function () { store(KEY_TOKEN, tokenEl.value.trim()); setup.open = false; });
  function needToken(section) {
    var t = read(KEY_TOKEN);
    if (!t) { setup.open = true; statusIn(section, "Add a GitHub token first (in the box at the top).", true); }
    return t;
  }
  function byName() { return who || (window.prompt("Your name, for the record:") || "").trim(); }
  function headers(token) {
    return { "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
  }
  function b64encode(str) { return btoa(unescape(encodeURIComponent(str))); }
  function b64decode(str) { return decodeURIComponent(escape(atob(str.replace(/\n/g, "")))); }
  function yamlStr(s) { return JSON.stringify(String(s)); }

  /* Read a file, transform its text, write it back; retries once on a 409 (someone else wrote first). */
  function putFile(path, transform, message, attempt) {
    var token = read(KEY_TOKEN);
    return fetch(api + "/contents/" + path + "?ref=main", { headers: headers(token) })
      .then(function (r) { if (r.status === 404) return null; if (!r.ok) throw new Error("read failed: " + r.status); return r.json(); })
      .then(function (cur) {
        var text = cur ? b64decode(cur.content) : "";
        var body = { message: message, content: b64encode(transform(text)), branch: "main" };
        if (cur) body.sha = cur.sha;
        return fetch(api + "/contents/" + path, { method: "PUT", headers: headers(token), body: JSON.stringify(body) });
      })
      .then(function (r) {
        if (r.status === 409 && !attempt) return putFile(path, transform, message, 1);
        if (!r.ok) throw new Error("write failed: " + r.status);
        return r;
      });
  }

  /* ---- queue: decisions append to approvals.yaml */
  var queue = document.getElementById("queue");
  var items = Array.prototype.slice.call(document.querySelectorAll(".rev"));
  var list = document.getElementById("rev-list");
  var countEl = document.getElementById("rev-count"), saveBtn = document.getElementById("rev-save");
  function decided() { return items.filter(function (it) { return it.getAttribute("data-decision") && !it.hasAttribute("data-saved"); }); }
  function refreshQueue() {
    var n = decided().length;
    countEl.textContent = n + (n === 1 ? " decision" : " decisions");
    saveBtn.disabled = n === 0;
    var left = items.filter(function (it) { return !it.hasAttribute("data-saved") && !it.hidden; }).length;
    document.getElementById("rev-empty").hidden = left > 0;
  }
  items.forEach(function (it) {
    it.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-decide]");
      if (btn) { var d = btn.getAttribute("data-decide"); it.setAttribute("data-decision", it.getAttribute("data-decision") === d ? "" : d); refreshQueue(); return; }
      if (e.target.closest("[data-ask]")) { window.location.href = "mailto:?subject=" + encodeURIComponent("Your event on Slack Tide: " + it.getAttribute("data-title")); }
    });
  });
  var qSource = document.getElementById("q-source"), qSort = document.getElementById("q-sort");
  function applyQueue() {
    var src = qSource.value;
    items.forEach(function (it) { it.hidden = !!src && it.getAttribute("data-source") !== src; });
    var key = qSort.value;
    var sorted = items.slice().sort(function (a, b) {
      var ka = key === "town" ? a.getAttribute("data-town") : key === "source" ? a.getAttribute("data-source") : a.getAttribute("data-start");
      var kb = key === "town" ? b.getAttribute("data-town") : key === "source" ? b.getAttribute("data-source") : b.getAttribute("data-start");
      return ka < kb ? -1 : ka > kb ? 1 : a.getAttribute("data-start") < b.getAttribute("data-start") ? -1 : 1;
    });
    sorted.forEach(function (it) { list.appendChild(it); });
    refreshQueue();
  }
  qSource.addEventListener("change", applyQueue); qSort.addEventListener("change", applyQueue);
  saveBtn.addEventListener("click", function () {
    if (!needToken(queue)) return;
    var by = byName(); if (!by) return;
    var toSave = decided(); saveBtn.disabled = true; statusIn(queue, "Saving…");
    var today = new Date().toISOString().slice(0, 10);
    var entries = toSave.map(function (it) {
      var lines = ["- id: " + yamlStr(it.getAttribute("data-id")), "  status: " + it.getAttribute("data-decision"),
                   "  by: " + yamlStr(by), "  date: " + yamlStr(today), "  title: " + yamlStr(it.getAttribute("data-title"))];
      if (it.getAttribute("data-venue")) lines.push("  venue: " + yamlStr(it.getAttribute("data-venue")));
      return lines.join("\n");
    }).join("\n") + "\n";
    putFile(paths.approvals, function (text) {
      if (!text) text = "# Approval decisions. One entry per series id; the last entry for an id wins.\n";
      if (text[text.length - 1] !== "\n") text += "\n";
      return text + entries;
    }, "Review: " + toSave.length + " decision" + (toSave.length === 1 ? "" : "s") + " by " + by)
      .then(function () { toSave.forEach(function (it) { it.setAttribute("data-saved", "1"); it.hidden = true; }); refreshQueue(); statusIn(queue, "Saved " + toSave.length + ". The site updates on the next pipeline run."); })
      .catch(function (e) { saveBtn.disabled = false; statusIn(queue, String(e.message || e), true); });
  });
  refreshQueue();

  /* ---- sources: the tracker rows save back to the CSV */
  var sourcesSec = document.getElementById("sources");
  var trkRows = Array.prototype.slice.call(document.querySelectorAll("#trk tr.trk"));
  var trkCount = document.getElementById("trk-count"), trkSave = document.getElementById("trk-save");
  var edits = {};   /* row index -> {field: value} */
  function refreshTracker() { var n = Object.keys(edits).length; trkCount.textContent = n + (n === 1 ? " change" : " changes"); trkSave.disabled = n === 0; }
  trkRows.forEach(function (tr) {
    Array.prototype.forEach.call(tr.querySelectorAll("[data-field]"), function (el) {
      el.addEventListener("change", function () {
        var i = tr.getAttribute("data-row"); edits[i] = edits[i] || {}; edits[i][el.getAttribute("data-field")] = el.value; refreshTracker();
      });
    });
  });
  ["t-town", "t-wave", "t-action"].forEach(function (id) { document.getElementById(id).addEventListener("change", applyTracker); });
  function applyTracker() {
    var town = document.getElementById("t-town").value, wave = document.getElementById("t-wave").value, action = document.getElementById("t-action").value;
    trkRows.forEach(function (tr) {
      var sel = tr.querySelector("[data-field='Action']");
      tr.hidden = (town && tr.getAttribute("data-town") !== town) || (wave && tr.getAttribute("data-wave") !== wave) || (action && sel.value !== action);
    });
  }
  /* CSV helpers: RFC 4180, quotes doubled, fields with commas, quotes or newlines quoted. */
  function parseCsv(text) {
    var rows = [], row = [], field = "", q = false;
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (q) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
      else if (c === '"') q = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c !== "\r") field += c;
    }
    if (field.length || row.length) { row.push(field); rows.push(row); }
    return rows;
  }
  function csvField(v) { v = String(v == null ? "" : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  trkSave.addEventListener("click", function () {
    if (!needToken(sourcesSec)) return;
    trkSave.disabled = true; statusIn(sourcesSec, "Saving…");
    var n = Object.keys(edits).length;
    putFile(paths.tracker, function (text) {
      var rows = parseCsv(text), header = rows[0];
      Object.keys(edits).forEach(function (i) {
        var r = rows[1 + Number(i)]; if (!r) return;
        Object.keys(edits[i]).forEach(function (field) { var c = header.indexOf(field); if (c >= 0) r[c] = edits[i][field]; });
      });
      return rows.map(function (r) { return r.map(csvField).join(","); }).join("\n") + "\n";
    }, "Tracker: " + n + " change" + (n === 1 ? "" : "s") + (who ? " by " + who : ""))
      .then(function () { edits = {}; refreshTracker(); statusIn(sourcesSec, "Saved. Regenerate the spreadsheet with pipeline/tools/tracker_xlsx.py when you need it."); })
      .catch(function (e) { trkSave.disabled = false; statusIn(sourcesSec, String(e.message || e), true); });
  });
  refreshTracker();

  /* ---- runs: start the pipeline */
  Array.prototype.forEach.call(document.querySelectorAll("[data-run]"), function (btn) {
    btn.addEventListener("click", function () {
      var section = btn.closest(".adm-section");
      var token = needToken(section); if (!token) return;
      statusIn(section, "Starting the pipeline…");
      fetch(api + "/actions/workflows/" + workflow + "/dispatches", { method: "POST", headers: headers(token), body: JSON.stringify({ ref: "main" }) })
        .then(function (r) { if (r.status === 204) statusIn(section, "Pipeline started. The site rebuilds and deploys in a few minutes."); else throw new Error("could not start the pipeline: " + r.status); })
        .catch(function (e) { statusIn(section, String(e.message || e), true); });
    });
  });

  /* ---- people: approvers.yaml */
  var people = document.getElementById("people"), form = document.getElementById("ppl-form");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!form.checkValidity()) { form.reportValidity(); return; }
    if (!needToken(people)) return;
    var name = document.getElementById("ap-name").value.trim(), email = document.getElementById("ap-email").value.trim().toLowerCase(), role = document.getElementById("ap-role").value;
    statusIn(people, "Saving…");
    var today = new Date().toISOString().slice(0, 10);
    putFile(paths.approvers, function (text) {
      if (text && text[text.length - 1] !== "\n") text += "\n";
      return text + "- name: " + yamlStr(name) + "\n  email: " + yamlStr(email) + "\n  role: " + role + "\n  added: " + yamlStr(today) + "\n";
    }, "Approvers: add " + email + (who ? " (by " + who + ")" : ""))
      .then(function () {
        var tr = document.createElement("tr"); tr.setAttribute("data-email", email);
        tr.innerHTML = '<td class="t"></td><td></td><td><span class="tag ' + (role === "admin" ? "ok" : "src") + '"></span></td><td></td><td></td>';
        tr.children[0].textContent = name; tr.children[1].textContent = email; tr.children[2].firstChild.textContent = role; tr.children[3].textContent = today;
        document.querySelector("#ppl tbody").appendChild(tr); form.reset();
        statusIn(people, "Added to approvers.yaml. Now add " + email + " to the Access policy in Cloudflare.");
      })
      .catch(function (err) { statusIn(people, String(err.message || err), true); });
  });
  document.getElementById("ppl").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-remove]"); if (!btn) return;
    var tr = btn.closest("tr"), email = tr.getAttribute("data-email");
    if (!window.confirm("Remove " + email + " from the approvers list?")) return;
    if (!needToken(people)) return;
    statusIn(people, "Saving…");
    putFile(paths.approvers, function (text) {
      /* drop the entry whose email line matches; entries start at "- name:" */
      var blocks = text.split(/\n(?=- )/), kept = blocks.filter(function (b) { return b.indexOf("email: " + email) < 0 && b.indexOf('email: "' + email + '"') < 0; });
      return kept.join("\n") + (text.endsWith("\n") ? "" : "\n");
    }, "Approvers: remove " + email + (who ? " (by " + who + ")" : ""))
      .then(function () { tr.remove(); statusIn(people, "Removed from approvers.yaml. Remove " + email + " from the Access policy in Cloudflare too."); })
      .catch(function (err) { statusIn(people, String(err.message || err), true); });
  });
})();
