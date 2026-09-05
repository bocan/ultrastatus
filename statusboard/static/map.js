/* Pan and zoom for the inline SVG map. Pure math first, DOM second.
   No dependencies. Loaded inline by render.py. */
(function () {
  "use strict";

  var MIN_SCALE = 1, MAX_SCALE = 8, FIT_MARGIN = 0.05;
  var CARD_GAP = 4, CARD_FLIP_X = 700, CARD_FLIP_Y = 260, CARD_LIFT = 10;
  var LABEL_ZOOM = 5, PRESET_ANIMATE_MS = 250, DRAG_THRESHOLD_PX = 3;

  function clampScale(s) { return Math.min(MAX_SCALE, Math.max(MIN_SCALE, s)); }

  /* Keep the transformed map covering the whole view box. */
  function clampState(st, view) {
    var s = clampScale(st.scale);
    var minTx = (view.x + view.w) * (1 - s), maxTx = view.x * (1 - s);
    var minTy = (view.y + view.h) * (1 - s), maxTy = view.y * (1 - s);
    return { scale: s,
             tx: Math.min(maxTx, Math.max(minTx, st.tx)),
             ty: Math.min(maxTy, Math.max(minTy, st.ty)) };
  }

  /* Zoom by factor keeping the view-box point (px, py) fixed under the cursor. */
  function zoomAt(st, factor, px, py, view) {
    var s2 = clampScale(st.scale * factor), k = s2 / st.scale;
    return clampState({ scale: s2, tx: px - (px - st.tx) * k, ty: py - (py - st.ty) * k }, view);
  }

  function panBy(st, dx, dy, view) {
    return clampState({ scale: st.scale, tx: st.tx + dx, ty: st.ty + dy }, view);
  }

  /* Frame a canvas box {x, y, w, h} inside the view with a 5% margin. */
  function fitBox(box, view) {
    var s = clampScale(Math.min(view.w / (box.w * (1 + 2 * FIT_MARGIN)), view.h / (box.h * (1 + 2 * FIT_MARGIN))));
    var cx = box.x + box.w / 2, cy = box.y + box.h / 2;
    var vx = view.x + view.w / 2, vy = view.y + view.h / 2;
    return clampState({ scale: s, tx: vx - cx * s, ty: vy - cy * s }, view);
  }

  /* Card placement in percentages, same rules as mapgen.card_style, from a screen-space point. */
  function cardStyle(sx, sy, view) {
    var style = {};
    if (sx <= CARD_FLIP_X) style.left = ((sx + CARD_GAP) / view.w * 100).toFixed(1) + "%";
    else style.right = ((view.w - sx + CARD_GAP) / view.w * 100).toFixed(1) + "%";
    if (sy - view.y <= CARD_FLIP_Y) style.top = ((sy - CARD_LIFT - view.y) / view.h * 100).toFixed(1) + "%";
    else style.bottom = ((view.y + view.h - sy - CARD_LIFT) / view.h * 100).toFixed(1) + "%";
    return style;
  }

  var MapMath = { clampScale: clampScale, clampState: clampState, zoomAt: zoomAt, panBy: panBy,
                  fitBox: fitBox, cardStyle: cardStyle };
  if (typeof window !== "undefined") window.MapMath = MapMath;
  if (typeof module !== "undefined" && module.exports) module.exports = MapMath;
  if (typeof document === "undefined") return;

  /* ---------- DOM ---------- */

  var svg = document.querySelector("svg.map");
  if (!svg) return;
  var viewport = svg.querySelector("g.viewport");
  var toolbar = document.querySelector(".map-toolbar");
  var vb = svg.getAttribute("viewBox").split(/\s+/).map(Number);
  var view = { x: vb[0], y: vb[1], w: vb[2], h: vb[3] };
  var presets = {};
  try { presets = JSON.parse(svg.getAttribute("data-presets") || "{}"); } catch (e) { presets = {}; }

  var circles = Array.prototype.slice.call(svg.querySelectorAll("circle.marker"));
  var labels = Array.prototype.slice.call(svg.querySelectorAll("text.label"));
  var cards = Array.prototype.slice.call(svg.querySelectorAll(".card"));
  var baseRadius = circles.map(function (c) { return Number(c.getAttribute("r")); });
  var cardByKey = {};
  cards.forEach(function (card) { cardByKey[card.getAttribute("data-key")] = card; });

  var state = { scale: 1, tx: 0, ty: 0 };
  var pinned = null;

  function toBox(preset) {
    var b = presets[preset];
    return b ? { x: b[0], y: b[1], w: b[2], h: b[3] } : null;
  }

  function repositionCards() {
    cards.forEach(function (card) {
      var cx = Number(card.getAttribute("data-x")), cy = Number(card.getAttribute("data-y"));
      var sx = cx * state.scale + state.tx, sy = cy * state.scale + state.ty;
      var style = cardStyle(sx, sy, view);
      card.style.left = style.left || ""; card.style.right = style.right || "";
      card.style.top = style.top || ""; card.style.bottom = style.bottom || "";
    });
  }

  function apply(animate) {
    state = clampState(state, view);
    viewport.classList.toggle("animate", !!animate);
    viewport.style.transform = "translate(" + state.tx + "px, " + state.ty + "px) scale(" + state.scale + ")";
    var s = state.scale;
    circles.forEach(function (c, i) {
      c.setAttribute("r", (baseRadius[i] / s).toFixed(2));
      c.style.strokeWidth = (1 / s).toFixed(3);
    });
    labels.forEach(function (t) { t.style.fontSize = (11 / s).toFixed(2) + "px"; });
    svg.classList.toggle("zoomed", s >= LABEL_ZOOM);
    repositionCards();
    try { localStorage.setItem("statusboard.view", JSON.stringify(state)); } catch (e) { /* private mode */ }
    if (animate) setTimeout(function () { viewport.classList.remove("animate"); }, PRESET_ANIMATE_MS);
  }

  /* Client pixels to view-box units. */
  function toCanvas(clientX, clientY) {
    var ctm = svg.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    var p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  function goPreset(name, animate) {
    var box = toBox(name) || toBox("world");
    if (!box) return;
    state = fitBox(box, view);
    apply(animate);
    if (history.replaceState) history.replaceState(null, "", "#view=" + name);
  }

  function setPinned(card) {
    if (pinned && pinned !== card) pinned.classList.remove("pinned");
    pinned = card || null;
    if (pinned) pinned.classList.add("pinned");
  }

  /* Wheel zoom at the cursor. */
  svg.addEventListener("wheel", function (e) {
    e.preventDefault();
    var p = toCanvas(e.clientX, e.clientY);
    state = zoomAt(state, e.deltaY < 0 ? 1.2 : 1 / 1.2, p.x, p.y, view);
    apply(false);
  }, { passive: false });

  /* Pointer drag, click-to-pin, and pinch. */
  var pointers = {}, dragStart = null, dragged = false, pinchStart = null;

  function pointerList() { return Object.keys(pointers).map(function (k) { return pointers[k]; }); }

  svg.addEventListener("pointerdown", function (e) {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
    svg.setPointerCapture(e.pointerId);
    var list = pointerList();
    if (list.length === 1) {
      dragStart = { x: e.clientX, y: e.clientY, target: e.target };
      dragged = false;
    } else if (list.length === 2) {
      pinchStart = { dist: Math.hypot(list[0].x - list[1].x, list[0].y - list[1].y), scale: state.scale };
    }
  });

  svg.addEventListener("pointermove", function (e) {
    if (!pointers[e.pointerId]) return;
    var prev = pointers[e.pointerId];
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
    var list = pointerList();
    if (list.length === 2 && pinchStart) {
      var dist = Math.hypot(list[0].x - list[1].x, list[0].y - list[1].y);
      var mid = toCanvas((list[0].x + list[1].x) / 2, (list[0].y + list[1].y) / 2);
      var target = clampScale(pinchStart.scale * dist / pinchStart.dist);
      state = zoomAt(state, target / state.scale, mid.x, mid.y, view);
      apply(false);
      dragged = true;
      return;
    }
    if (list.length === 1 && dragStart) {
      if (!dragged && Math.hypot(e.clientX - dragStart.x, e.clientY - dragStart.y) < DRAG_THRESHOLD_PX) return;
      dragged = true;
      var a = toCanvas(prev.x, prev.y), b = toCanvas(e.clientX, e.clientY);
      state = panBy(state, b.x - a.x, b.y - a.y, view);
      apply(false);
    }
  });

  function endPointer(e) {
    if (!pointers[e.pointerId]) return;
    delete pointers[e.pointerId];
    if (pointerList().length < 2) pinchStart = null;
    if (pointerList().length === 0) {
      if (!dragged && dragStart) {
        var circle = dragStart.target.closest ? dragStart.target.closest("circle.marker") : null;
        if (circle) {
          var card = cardByKey[circle.getAttribute("data-key")];
          setPinned(pinned === card ? null : card);
        } else if (!(dragStart.target.closest && dragStart.target.closest(".card"))) {
          setPinned(null);
        }
      }
      dragStart = null;
      dragged = false;
    }
  }
  svg.addEventListener("pointerup", endPointer);
  svg.addEventListener("pointercancel", endPointer);

  svg.addEventListener("dblclick", function (e) {
    e.preventDefault();
    var p = toCanvas(e.clientX, e.clientY);
    state = zoomAt(state, 2, p.x, p.y, view);
    apply(false);
  });

  /* Keyboard, only while the map or its toolbar has focus. */
  function onKey(e) {
    var cx = view.x + view.w / 2, cy = view.y + view.h / 2;
    switch (e.key) {
      case "+": case "=": state = zoomAt(state, 1.5, cx, cy, view); break;
      case "-": case "_": state = zoomAt(state, 1 / 1.5, cx, cy, view); break;
      case "ArrowLeft": state = panBy(state, view.w * 0.1, 0, view); break;
      case "ArrowRight": state = panBy(state, -view.w * 0.1, 0, view); break;
      case "ArrowUp": state = panBy(state, 0, view.h * 0.1, view); break;
      case "ArrowDown": state = panBy(state, 0, -view.h * 0.1, view); break;
      case "0": goPreset("world", true); return;
      case "Escape": setPinned(null); return;
      default: return;
    }
    e.preventDefault();
    apply(false);
  }
  svg.addEventListener("keydown", onKey);
  if (toolbar) toolbar.addEventListener("keydown", onKey);

  /* Toolbar. */
  if (toolbar) {
    toolbar.removeAttribute("hidden");
    toolbar.addEventListener("click", function (e) {
      var button = e.target.closest ? e.target.closest("button") : null;
      if (!button) return;
      if (button.hasAttribute("data-preset")) goPreset(button.getAttribute("data-preset"), true);
      else if (button.getAttribute("data-zoom") === "in") { state = zoomAt(state, 1.5, view.x + view.w / 2, view.y + view.h / 2, view); apply(false); }
      else if (button.getAttribute("data-zoom") === "out") { state = zoomAt(state, 1 / 1.5, view.x + view.w / 2, view.y + view.h / 2, view); apply(false); }
    });
  }

  /* Initial view: hash, then saved state, then world. */
  var hash = (location.hash.match(/view=([a-z-]+)/) || [])[1];
  if (hash && toBox(hash)) {
    state = fitBox(toBox(hash), view);
    apply(false);
  } else {
    var restored = false;
    try {
      var saved = JSON.parse(localStorage.getItem("statusboard.view") || "null");
      if (saved && typeof saved.scale === "number") { state = clampState(saved, view); restored = true; }
    } catch (e) { /* ignore */ }
    if (!restored) state = fitBox(toBox("world") || { x: view.x, y: view.y, w: view.w, h: view.h }, view);
    apply(false);
  }
})();
