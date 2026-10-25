/* Slack Tide review queue. Decisions are appended to approvals.yaml in the repository through
   the GitHub contents API with a token the approver keeps in this browser. No server. */
(function () {
  "use strict";
  var main = document.querySelector("main.review");
  if (!main) return;
  var repo = main.getAttribute("data-repo");
  var path = main.getAttribute("data-approvals");
  var workflow = main.getAttribute("data-workflow");
  var api = "https://api.github.com/repos/" + repo;
  var KEY_TOKEN = "st.review.token", KEY_NAME = "st.review.name";

  function store(k, v) { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch (e) {} }
  function read(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } }

  var nameEl = document.getElementById("rev-name"), tokenEl = document.getElementById("rev-token");
  var setup = document.querySelector(".setup");
  nameEl.value = read(KEY_NAME); tokenEl.value = read(KEY_TOKEN);
  if (!nameEl.value || !tokenEl.value) setup.open = true;
  document.getElementById("rev-save-setup").addEventListener("click", function () {
    store(KEY_NAME, nameEl.value.trim()); store(KEY_TOKEN, tokenEl.value.trim());
    setup.open = false; status("Kept in this browser.");
  });

  var items = Array.prototype.slice.call(document.querySelectorAll(".rev"));
  var countEl = document.getElementById("rev-count"), saveBtn = document.getElementById("rev-save");
  var statusEl = document.getElementById("rev-status");
  function status(msg, bad) { statusEl.textContent = msg; statusEl.classList.toggle("is-bad", !!bad); }

  function decided() { return items.filter(function (it) { return it.getAttribute("data-decision") && !it.hasAttribute("data-saved"); }); }
  function refresh() {
    var n = decided().length;
    countEl.textContent = n + (n === 1 ? " decision" : " decisions");
    saveBtn.disabled = n === 0;
    var left = items.filter(function (it) { return !it.hasAttribute("data-saved"); }).length;
    document.getElementById("rev-empty").hidden = left > 0;
  }
  items.forEach(function (it) {
    it.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-decide]");
      if (!btn) return;
      var d = btn.getAttribute("data-decide");
      it.setAttribute("data-decision", it.getAttribute("data-decision") === d ? "" : d);
      refresh();
    });
  });

  function yamlStr(s) { return JSON.stringify(String(s)); }   /* a JSON string is a valid YAML double-quoted scalar */
  function entries(by, today) {
    return decided().map(function (it) {
      var lines = ["- id: " + yamlStr(it.getAttribute("data-id")),
                   "  status: " + it.getAttribute("data-decision"),
                   "  by: " + yamlStr(by), "  date: " + yamlStr(today),
                   "  title: " + yamlStr(it.getAttribute("data-title"))];
      if (it.getAttribute("data-venue")) lines.push("  venue: " + yamlStr(it.getAttribute("data-venue")));
      return lines.join("\n");
    }).join("\n") + "\n";
  }
  function b64encode(str) { return btoa(unescape(encodeURIComponent(str))); }
  function b64decode(str) { return decodeURIComponent(escape(atob(str.replace(/\n/g, "")))); }
  function headers(token) {
    return { "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
  }

  function save(attempt) {
    var token = read(KEY_TOKEN), by = read(KEY_NAME);
    if (!token || !by) { setup.open = true; status("Add your name and a token first.", true); return; }
    var toSave = decided();
    if (!toSave.length) return;
    saveBtn.disabled = true; status("Saving…");
    var today = new Date().toISOString().slice(0, 10);
    fetch(api + "/contents/" + path + "?ref=main", { headers: headers(token) })
      .then(function (r) { if (r.status === 404) return null; if (!r.ok) throw new Error("read failed: " + r.status); return r.json(); })
      .then(function (cur) {
        var text = cur ? b64decode(cur.content) : "# Approval decisions. One entry per series id; the last entry for an id wins.\n";
        if (text.length && text[text.length - 1] !== "\n") text += "\n";
        var body = { message: "Review: " + toSave.length + " decision" + (toSave.length === 1 ? "" : "s") + " by " + by,
                     content: b64encode(text + entries(by, today)), branch: "main" };
        if (cur) body.sha = cur.sha;
        return fetch(api + "/contents/" + path, { method: "PUT", headers: headers(token), body: JSON.stringify(body) });
      })
      .then(function (r) {
        if (r.status === 409 && attempt < 2) { status("The file moved under us; trying again…"); return save(attempt + 1); }
        if (!r.ok) throw new Error("write failed: " + r.status);
        toSave.forEach(function (it) { it.setAttribute("data-saved", "1"); });
        refresh();
        status("Saved " + toSave.length + ". The site updates on the next pipeline run.");
      })
      .catch(function (e) { saveBtn.disabled = false; status(String(e.message || e), true); });
  }
  saveBtn.addEventListener("click", function () { save(0); });

  document.getElementById("rev-run").addEventListener("click", function () {
    var token = read(KEY_TOKEN);
    if (!token) { setup.open = true; status("Add a token first.", true); return; }
    status("Starting the pipeline…");
    fetch(api + "/actions/workflows/" + workflow + "/dispatches", { method: "POST", headers: headers(token), body: JSON.stringify({ ref: "main" }) })
      .then(function (r) {
        if (r.status === 204) status("Pipeline started. The site rebuilds in a few minutes.");
        else throw new Error("could not start the pipeline: " + r.status);
      })
      .catch(function (e) { status(String(e.message || e), true); });
  });
  refresh();
})();
