/* Slack Tide, Map view. Leaflet (vendored, assets/vendor/leaflet) over the place cards the build
   writes into the page: one pin per .place, read from its data attributes, so the pins and the
   list are the same records. site.js owns the town select and the category tiles and announces
   each change as a "st:filter" event; this file filters the places and redraws the pins. */
(function () {
  "use strict";

  var el = document.getElementById("map");
  if (!el || typeof L === "undefined") return;
  var places = Array.prototype.slice.call(document.querySelectorAll(".place[data-lat]"));
  var SHOW = +el.getAttribute("data-show") || 3;
  var state = { town: "", cat: "" };
  var b = (el.getAttribute("data-bounds") || "41.45,-71.3,41.85,-70.55").split(",").map(Number);
  var REGION = [[b[0], b[1]], [b[2], b[3]]];

  var map = L.map(el, { scrollWheelZoom: false, zoomControl: true, attributionControl: true });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" rel="noopener" target="_blank">Leaflet</a>');
  L.tileLayer(el.getAttribute("data-tiles"), {
    attribution: el.getAttribute("data-attribution") || "",
    subdomains: el.getAttribute("data-subdomains") || "abc",
    maxZoom: 19
  }).addTo(map);
  /* The wheel zooms once the map has been clicked or tapped, so the page still scrolls past it. */
  map.on("focus click", function () { map.scrollWheelZoom.enable(); });
  map.on("blur", function () { map.scrollWheelZoom.disable(); });
  var layer = L.layerGroup().addTo(map);
  var markers = {};

  function visibleEvents(place) {
    return Array.prototype.filter.call(place.querySelectorAll(".place-ev"), function (e) { return !e.hidden && !e.hasAttribute("data-folded"); });
  }
  function matchingEvents(place) {
    return Array.prototype.filter.call(place.querySelectorAll(".place-ev"), function (e) { return !e.hidden; });
  }
  function colourVar(place) {
    var fam = state.cat || place.getAttribute("data-family");
    return fam ? "var(--st-cat-" + fam + ")" : "var(--st-paper)";
  }

  /* The pin: the view button's pin shape, filled in the place's category colour with the count
     inside, a hard ink offset behind it like the buttons; a dashed outline for a town-centre pin. */
  function pinIcon(place, count) {
    var approx = place.getAttribute("data-approx") === "1";
    var d = "M14 34s-12-11.2-12-20.5a12 12 0 0 1 24 0C26 22.8 14 34 14 34z";
    var html = '<svg viewBox="0 0 30 38" width="30" height="38" aria-hidden="true">' +
      '<path d="' + d + '" transform="translate(2 2)" fill="var(--st-ink)"/>' +
      '<path d="' + d + '" fill="' + colourVar(place) + '" stroke="var(--st-ink)" stroke-width="1.5"' + (approx ? ' stroke-dasharray="3 2"' : "") + "/>" +
      '<text x="14" y="17.5" text-anchor="middle" font-family="IBM Plex Mono, Menlo, monospace" font-size="11" font-weight="500" fill="var(--st-ink)">' + count + "</text></svg>";
    return L.divIcon({ className: "st-pin" + (approx ? " is-approx" : ""), html: html, iconSize: [30, 38], iconAnchor: [14, 34], popupAnchor: [1, -30] });
  }

  function popupFor(place) {
    var box = document.createElement("div");
    box.className = "st-popup";
    var name = document.createElement("div");
    name.className = "pp-name";
    name.innerHTML = place.querySelector(".place-name").innerHTML;
    box.appendChild(name);
    var where = document.createElement("div");
    where.className = "pp-where";
    var addr = place.querySelector(".place-addr");
    where.textContent = addr ? addr.textContent : place.getAttribute("data-town");
    box.appendChild(where);
    var evs = matchingEvents(place);
    var list = document.createElement("div");
    list.className = "place-events";
    evs.slice(0, SHOW).forEach(function (e) { var c = e.cloneNode(true); c.hidden = false; c.removeAttribute("data-folded"); list.appendChild(c); });
    box.appendChild(list);
    if (evs.length > SHOW) {
      var more = document.createElement("a");
      more.className = "pp-more";
      more.href = "#" + place.id;
      more.textContent = "+" + (evs.length - SHOW) + " more in the list";
      more.addEventListener("click", function () { place.setAttribute("data-expanded", ""); applyPlaceFilters(false); });
      box.appendChild(more);
    }
    return box;
  }

  function highlight(place) {
    places.forEach(function (q) { q.classList.toggle("is-active", q === place); });
  }

  function render() {
    layer.clearLayers();
    markers = {};
    var bounds = [];
    places.forEach(function (p) {
      if (p.hidden) return;
      var n = matchingEvents(p).length;
      var ll = [+p.getAttribute("data-lat"), +p.getAttribute("data-lon")];
      var m = L.marker(ll, { icon: pinIcon(p, n), title: p.querySelector(".place-name").textContent.trim(), keyboard: true, riseOnHover: true });
      m.bindPopup(function () { return popupFor(p); }, { maxWidth: 300, minWidth: 220, className: "st-popup-wrap", autoPanPadding: [24, 24] });
      m.on("click", function () { highlight(p); });
      m.addTo(layer);
      markers[p.getAttribute("data-place")] = m;
      bounds.push(ll);
    });
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [36, 36], maxZoom: 15 });
    else if (bounds.length === 1) map.setView(bounds[0], 14);
    else map.fitBounds(REGION);
  }

  /* Places and their listings follow the town select and the category tiles: a listing shows
     when its family matches, a place shows when it is in the town and has a listing showing. The
     first SHOW listings show, the rest fold behind "+N more" until the place is expanded. */
  function applyPlaceFilters(redraw) {
    var shown = 0;
    places.forEach(function (p) {
      var townOk = !state.town || p.getAttribute("data-town") === state.town;
      var expanded = p.hasAttribute("data-expanded"), n = 0;
      Array.prototype.forEach.call(p.querySelectorAll(".place-ev"), function (e) {
        var on = townOk && (!state.cat || e.getAttribute("data-cat") === state.cat);
        e.hidden = !on;
        if (on) { n++; if (!expanded && n > SHOW) e.setAttribute("data-folded", ""); else e.removeAttribute("data-folded"); }
      });
      p.hidden = !townOk || n === 0;
      if (!p.hidden) shown++;
      var more = p.querySelector(".place-more");
      if (more) { more.hidden = expanded || n <= SHOW; more.textContent = "+" + Math.max(n - SHOW, 0) + " more"; }
    });
    var count = document.getElementById("places-count");
    if (count) count.textContent = shown + (shown === 1 ? " place" : " places");
    var empty = document.getElementById("map-empty");
    if (empty) empty.hidden = shown > 0;
    if (redraw !== false) render();
  }

  places.forEach(function (p) {
    var head = p.querySelector(".place-head");
    head.addEventListener("click", function (e) {
      if (e.target.closest("a")) return;   /* the name's link goes to the venue's site */
      var m = markers[p.getAttribute("data-place")];
      if (!m) return;
      highlight(p);
      map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 14), { duration: 0.6 });
      map.once("moveend", function () { m.openPopup(); });
      if (window.innerWidth < 700) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    var more = p.querySelector(".place-more");
    if (more) more.addEventListener("click", function () { p.setAttribute("data-expanded", ""); applyPlaceFilters(false); });
  });

  document.addEventListener("st:filter", function (e) {
    state = { town: e.detail.town || "", cat: e.detail.cat || "" };
    applyPlaceFilters(true);
  });

  applyPlaceFilters(true);
})();
