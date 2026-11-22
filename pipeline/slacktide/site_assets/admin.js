/* Slack Tide admin page. Four tabs over server-rendered markup. Who is signed in comes from
   Cloudflare Access, which fronts /admin/; every save goes to the admin service, a Cloudflare
   Worker on /admin/api/ behind the same gate (worker/ in the repository), which checks the
   visitor's Access identity and makes the commit itself. No token is kept in the browser.
   Writes: approvals.yaml (append), docs/sources-tracker.csv (rewrite rows), approvers.yaml
   (append or remove), and a workflow dispatch for the pipeline. */
(function () {
  "use strict";
  var main = document.querySelector("main.admin");
  if (!main) return;
  var API = "/admin/api/";
  var who = "";   /* the signed-in email, from Access; empty on a local build */
  var NOT_LIVE = "Saving is only possible on the live site, behind the login gate.";

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
  function notLive() {
    whoEl.textContent = "Not behind the login gate (a local build, or the gate is off). " + NOT_LIVE;
  }
  fetch("/cdn-cgi/access/get-identity", { credentials: "include" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (id) {
      if (id && id.email) {
        who = id.email; whoEl.innerHTML = "";
        whoEl.appendChild(document.createTextNode("Signed in as "));
        var b = document.createElement("b"); b.textContent = who; whoEl.appendChild(b);
        whoEl.appendChild(document.createTextNode(" through Cloudflare Access; saves are recorded under this address · "));
        var a = document.createElement("a"); a.href = "/cdn-cgi/access/logout"; a.textContent = "sign out"; whoEl.appendChild(a);
      } else notLive();
    })
    .catch(notLive);

  /* ---- the admin service: same origin, the Access cookie goes along, JSON both ways */
  function needLive(section) {
    if (!who) statusIn(section, NOT_LIVE, true);
    return !!who;
  }
  function call(path, method, body) {
    var init = { method: method, credentials: "include", headers: { "Accept": "application/json" } };
    if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    return fetch(API + path, init).then(function (r) {
      var ct = r.headers.get("Content-Type") || "";
      if (ct.indexOf("application/json") < 0) {
        throw new Error(r.status === 404 ? "The admin service is not deployed on this hostname yet (see worker/README.md)."
                        : r.status === 401 || r.status === 403 ? "Your sign-in has lapsed. Reload the page to sign in again."
                        : "The admin service answered " + r.status + ".");
      }
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || ("The admin service answered " + r.status + "."));
        return data;
      });
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
    if (!needLive(queue)) return;
    var toSave = decided(); saveBtn.disabled = true; statusIn(queue, "Saving…");
    var decisions = toSave.map(function (it) {
      return { id: it.getAttribute("data-id"), status: it.getAttribute("data-decision"),
               title: it.getAttribute("data-title"), venue: it.getAttribute("data-venue") || "" };
    });
    call("decisions", "POST", { decisions: decisions })
      .then(function (out) { toSave.forEach(function (it) { it.setAttribute("data-saved", "1"); it.hidden = true; }); refreshQueue(); statusIn(queue, "Saved " + out.saved + " as " + out.by + ". The site updates on the next pipeline run."); })
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
  trkSave.addEventListener("click", function () {
    if (!needLive(sourcesSec)) return;
    trkSave.disabled = true; statusIn(sourcesSec, "Saving…");
    call("tracker", "POST", { edits: edits })
      .then(function () { edits = {}; refreshTracker(); statusIn(sourcesSec, "Saved. Regenerate the spreadsheet with pipeline/tools/tracker_xlsx.py when you need it."); })
      .catch(function (e) { trkSave.disabled = false; statusIn(sourcesSec, String(e.message || e), true); });
  });
  refreshTracker();

  /* ---- runs: start the pipeline */
  Array.prototype.forEach.call(document.querySelectorAll("[data-run]"), function (btn) {
    btn.addEventListener("click", function () {
      var section = btn.closest(".adm-section");
      if (!needLive(section)) return;
      statusIn(section, "Starting the pipeline…");
      call("run", "POST")
        .then(function () { statusIn(section, "Pipeline started. The site rebuilds and deploys in a few minutes."); })
        .catch(function (e) { statusIn(section, String(e.message || e), true); });
    });
  });

  /* ---- people: approvers.yaml */
  var people = document.getElementById("people"), form = document.getElementById("ppl-form");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!form.checkValidity()) { form.reportValidity(); return; }
    if (!needLive(people)) return;
    var name = document.getElementById("ap-name").value.trim(), email = document.getElementById("ap-email").value.trim().toLowerCase(), role = document.getElementById("ap-role").value;
    statusIn(people, "Saving…");
    call("approvers", "POST", { name: name, email: email, role: role })
      .then(function (out) {
        var tr = document.createElement("tr"); tr.setAttribute("data-email", email);
        tr.innerHTML = '<td class="t"></td><td></td><td><span class="tag ' + (role === "admin" ? "ok" : "src") + '"></span></td><td></td><td><button type="button" class="rev-btn" data-remove>Remove</button></td>';
        tr.children[0].textContent = name; tr.children[1].textContent = email; tr.children[2].firstChild.textContent = role; tr.children[3].textContent = out.date || "";
        document.querySelector("#ppl tbody").appendChild(tr); form.reset();
        statusIn(people, "Added to approvers.yaml. Now add " + email + " to the Access policy in Cloudflare.");
      })
      .catch(function (err) { statusIn(people, String(err.message || err), true); });
  });
  document.getElementById("ppl").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-remove]"); if (!btn) return;
    var tr = btn.closest("tr"), email = tr.getAttribute("data-email");
    if (!window.confirm("Remove " + email + " from the approvers list?")) return;
    if (!needLive(people)) return;
    statusIn(people, "Saving…");
    call("approvers", "DELETE", { email: email })
      .then(function () { tr.remove(); statusIn(people, "Removed from approvers.yaml. Remove " + email + " from the Access policy in Cloudflare too."); })
      .catch(function (err) { statusIn(people, String(err.message || err), true); });
  });
})();
