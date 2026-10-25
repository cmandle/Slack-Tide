/* Slack Tide, Events section. Plain JavaScript: town and category filters over server-rendered
   markup, and a tide panel that follows the clock using the predictions embedded in the page. */
(function () {
  "use strict";

  var townSelect = document.getElementById("town");
  var tiles = Array.prototype.slice.call(document.querySelectorAll(".tile[data-cat]"));
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card[data-town]"));
  var rows = Array.prototype.slice.call(document.querySelectorAll(".week-row[data-town]"));
  var state = { town: "", cat: "" };

  function matches(el) {
    return (!state.town || el.getAttribute("data-town") === state.town) &&
           (!state.cat || el.getAttribute("data-cat") === state.cat);
  }

  function applyFilters() {
    var shown = 0, weekShown = 0;
    cards.forEach(function (c) { var on = matches(c); c.hidden = !on; if (on) shown++; });
    rows.forEach(function (r) { var on = matches(r); r.hidden = !on; if (on) weekShown++; });
    var tonightEmpty = document.getElementById("tonight-empty");
    if (tonightEmpty) tonightEmpty.hidden = shown > 0;
    var weekEmpty = document.getElementById("week-empty");
    if (weekEmpty) weekEmpty.hidden = weekShown > 0;
    tiles.forEach(function (t) {
      t.setAttribute("aria-pressed", t.getAttribute("data-cat") === state.cat ? "true" : "false");
    });
  }

  if (townSelect) {
    townSelect.addEventListener("change", function () { state.town = townSelect.value; applyFilters(); });
  }
  tiles.forEach(function (t) {
    t.addEventListener("click", function () {
      var cat = t.getAttribute("data-cat");
      state.cat = (state.cat === cat) ? "" : cat;
      applyFilters();
    });
  });

  /* Stickers drift aside while a section tab is hovered or focused. */
  var stickers = document.querySelector(".stickers");
  if (stickers) {
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
      ["mouseenter", "focus"].forEach(function (ev) { tab.addEventListener(ev, function () { stickers.classList.add("is-nudged"); }); });
      ["mouseleave", "blur"].forEach(function (ev) { tab.addEventListener(ev, function () { stickers.classList.remove("is-nudged"); }); });
    });
  }

  /* Add your event: the call to action opens the pop-up where <dialog> exists, else follows the link. */
  var dialog = document.getElementById("add-dialog");
  if (dialog && typeof dialog.showModal === "function") {
    Array.prototype.forEach.call(document.querySelectorAll("[data-dialog='add-dialog']"), function (cta) {
      cta.addEventListener("click", function (e) { e.preventDefault(); dialog.showModal(); });
    });
    Array.prototype.forEach.call(dialog.querySelectorAll("[data-close]"), function (b) { b.addEventListener("click", function () { dialog.close(); }); });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
  }

  /* The form posts to a Google Form when one is configured (data-action), else it opens the
     visitor's email client with the details filled in. The hidden "website" field catches bots. */
  function formData(form) {
    var d = {};
    ["title", "date", "start", "end", "venue", "town", "url", "cost", "description", "name", "email"].forEach(function (k) {
      var el = form.elements[k]; d[k] = el ? String(el.value || "").trim() : "";
    });
    return d;
  }
  function mailtoFor(form, d) {
    var lines = ["Event: " + d.title, "Date: " + d.date, "Start: " + d.start, "End: " + d.end, "Venue: " + d.venue,
                 "Town: " + d.town, "Link: " + d.url, "Cost: " + d.cost, "", d.description, "", "From: " + d.name + " <" + d.email + ">"];
    return form.getAttribute("data-contact") + "?subject=" + encodeURIComponent("Event for Slack Tide: " + d.title) +
           "&body=" + encodeURIComponent(lines.join("\n"));
  }
  Array.prototype.forEach.call(document.querySelectorAll("form.add-form"), function (form) {
    var statusEl = form.querySelector(".form-status");
    function say(msg, bad) { if (statusEl) { statusEl.textContent = msg; statusEl.classList.toggle("is-bad", !!bad); } }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (form.elements.website && form.elements.website.value) { say("Thank you. We will read it on Sunday."); form.reset(); return; }
      if (!form.checkValidity()) { form.reportValidity(); return; }
      var d = formData(form);
      var action = form.getAttribute("data-action");
      if (!action) { window.location.href = mailtoFor(form, d); say("Your email client should open with the details filled in."); return; }
      var fields = {};
      try { fields = JSON.parse(form.getAttribute("data-fields") || "{}"); } catch (err) {}
      var body = new FormData();
      Object.keys(fields).forEach(function (k) { if (d[k] !== undefined) body.append(fields[k], d[k]); });
      say("Sending…");
      fetch(action, { method: "POST", mode: "no-cors", body: body })
        .then(function () { say("Thank you. A person reads every submission, usually on Sunday."); form.reset(); })
        .catch(function () { say("That did not go through. Email us instead: " + form.getAttribute("data-contact").replace("mailto:", ""), true); });
    });
  });

  /* Tide panel */
  var panel = document.getElementById("tide");
  var dataEl = document.getElementById("tide-data");
  if (!panel || !dataEl) return;
  var tide;
  try { tide = JSON.parse(dataEl.textContent); } catch (e) { return; }

  function unavailable() {
    panel.setAttribute("data-state", "unavailable");
    var msg = panel.querySelector(".tide-unavailable");
    if (msg) msg.hidden = false;
    Array.prototype.forEach.call(panel.querySelectorAll(".tide-staff, .tide-readings"), function (el) { el.hidden = true; });
  }

  var fetched = Date.parse(tide.fetched_at);
  if (!isFinite(fetched) || Date.now() - fetched > tide.max_age_hours * 3600 * 1000) { unavailable(); return; }

  /* Predictions are stamped in the station's local time without an offset; compare them
     against the clock as the station sees it, using the offset embedded at build time. */
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function stationNow() {
    var local = new Date(Date.now() + tide.utc_offset_minutes * 60000);
    return local.getUTCFullYear() + "-" + pad(local.getUTCMonth() + 1) + "-" + pad(local.getUTCDate()) +
           " " + pad(local.getUTCHours()) + ":" + pad(local.getUTCMinutes());
  }
  function fmtTime(t) {
    var hm = t.slice(11).split(":"), h = +hm[0], m = hm[1];
    var ampm = h >= 12 ? "PM" : "AM"; h = h % 12; if (h === 0) h = 12;
    return h + ":" + m + " " + ampm;
  }

  function update() {
    var now = stationNow();
    var levels = tide.levels, cur = null, next = null;
    for (var i = 0; i < levels.length; i++) {
      if (levels[i].t <= now) cur = levels[i]; else { next = levels[i]; break; }
    }
    if (!cur) { unavailable(); return; }
    var v = cur.v;
    if (next) {
      var a = Date.parse(cur.t.replace(" ", "T") + "Z"), b = Date.parse(next.t.replace(" ", "T") + "Z");
      var n = Date.parse(now.replace(" ", "T") + ":00Z");
      if (b > a) v = cur.v + (next.v - cur.v) * Math.max(0, Math.min(1, (n - a) / (b - a)));
    }
    var trend = next ? (next.v > cur.v ? "rising" : next.v < cur.v ? "falling" : "slack") : "";
    var arrow = trend === "rising" ? "↑" : trend === "falling" ? "↓" : "→";
    var nowEl = panel.querySelector(".tide-now");
    if (nowEl) {
      nowEl.textContent = "";
      nowEl.appendChild(document.createTextNode(v.toFixed(1) + " ft " + arrow));
      if (trend) { var s = document.createElement("span"); s.className = "long"; s.textContent = " " + trend; nowEl.appendChild(s); }
    }

    var staff = panel.querySelector(".tide-staff");
    if (staff) {
      var min = +staff.getAttribute("data-min"), max = +staff.getAttribute("data-max");
      var top = +staff.getAttribute("data-top"), bottom = +staff.getAttribute("data-bottom");
      var y = bottom - (bottom - top) * Math.max(0, Math.min(1, (v - min) / (max - min)));
      var water = staff.querySelector(".tide-water");
      if (water) { water.setAttribute("y", y); water.setAttribute("height", bottom - y); }
      var mark = staff.querySelector(".tide-mark");
      if (mark) mark.setAttribute("transform", "translate(0 " + y + ")");
      staff.setAttribute("aria-label", "Tide staff, " + v.toFixed(1) + " feet" + (trend ? " and " + trend : ""));
    }

    var hilo = panel.querySelector(".tide-hilo");
    if (hilo) {
      var upcoming = tide.hilo.filter(function (h) { return h.t > now; }).slice(0, 2);
      if (upcoming.length) {
        hilo.textContent = "";
        upcoming.forEach(function (h, i) {
          if (i) { var sep = document.createElement("span"); sep.className = "sep"; sep.textContent = " · "; hilo.appendChild(sep); }
          var sp = document.createElement("span");
          sp.textContent = (h.type === "H" ? "High " : "Low ") + fmtTime(h.t);
          hilo.appendChild(sp);
        });
      }
    }
  }
  update();
  setInterval(update, 60000);
})();
