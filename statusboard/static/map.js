/* Pan and zoom for the inline SVG map. Pure math first, DOM second.
   No dependencies. Loaded inline by render.py. */
(function () {
  "use strict";

  var MIN_SCALE = 1, MAX_SCALE = 8, FIT_MARGIN = 0.05;
  var CARD_GAP = 4, CARD_FLIP_X = 700, CARD_FLIP_Y = 260, CARD_LIFT = 10;
  var LABEL_ZOOM = 5, PRESET_ANIMATE_MS = 250, DRAG_THRESHOLD_PX = 3, HINT_MS = 1400;
  /* One mouse notch is about 100 px of deltaY and should zoom about 1.15x.
     A trackpad fires many events of a few px each; scaling by the delta keeps
     that smooth instead of stacking a fixed factor per event. */
  var WHEEL_SENSITIVITY = 0.0014, WHEEL_MAX_STEP = 1.5;
  /* Label gap from the marker centre, in screen pixels. Labels live inside the
     zoomed group, so the gap is divided by the scale each frame, like the radius. */
  var LABEL_DX = 9, LABEL_DY = 4;

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

  /* Zoom factor for one wheel event, proportional to its delta. deltaMode 1 is
     lines, 2 is pages; both are converted to a pixel estimate first. */
  function wheelFactor(deltaY, deltaMode) {
    var px = deltaY * (deltaMode === 1 ? 16 : deltaMode === 2 ? 400 : 1);
    var f = Math.exp(-px * WHEEL_SENSITIVITY);
    return Math.min(WHEEL_MAX_STEP, Math.max(1 / WHEEL_MAX_STEP, f));
  }

  var MapMath = { clampScale: clampScale, clampState: clampState, zoomAt: zoomAt, panBy: panBy,
                  fitBox: fitBox, cardStyle: cardStyle, wheelFactor: wheelFactor };
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
  var centreX = circles.map(function (c) { return Number(c.getAttribute("cx")); });
  var centreY = circles.map(function (c) { return Number(c.getAttribute("cy")); });
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
    labels.forEach(function (t, i) {
      t.style.fontSize = (11 / s).toFixed(2) + "px";
      if (i < circles.length) {
        t.setAttribute("x", (centreX[i] + LABEL_DX / s).toFixed(2));
        t.setAttribute("y", (centreY[i] + LABEL_DY / s).toFixed(2));
      }
    });
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

  /* Cooperative gestures, the same rule as Google Maps and Mapbox embeds.
     A plain wheel over the map scrolls the page. The wheel zooms the map when
     Cmd or Ctrl is held, or after the map has been clicked or tapped. A click
     elsewhere, or Escape, hands the wheel back to the page. On touch, one
     finger scrolls the page until the map is tapped; then it drags the map. */
  var wrap = svg.closest(".map-wrap") || svg.parentNode;
  var hint = document.querySelector(".map-hint");
  var hintTimer = null;
  var active = false;
  var isMac = /Mac|iPhone|iPad/.test(navigator.platform || "");

  function setActive(on) {
    active = !!on;
    if (wrap && wrap.classList) wrap.classList.toggle("active", active);
    if (active) hideHint();
  }

  function showHint(text) {
    if (!hint) return;
    hint.textContent = text;
    hint.classList.add("show");
    clearTimeout(hintTimer);
    hintTimer = setTimeout(hideHint, HINT_MS);
  }

  function hideHint() {
    if (hint) hint.classList.remove("show");
  }

  document.addEventListener("pointerdown", function (e) {
    var inside = (wrap && wrap.contains(e.target)) || (toolbar && toolbar.contains(e.target));
    if (!inside && active) setActive(false);
  }, true);

  svg.addEventListener("wheel", function (e) {
    if (onCard(e.target)) return;  /* let a long card scroll the page instead of zooming */
    if (!(active || e.ctrlKey || e.metaKey)) {
      showHint("Use " + (isMac ? "Cmd" : "Ctrl") + " + scroll to zoom the map, or click the map first");
      return;  /* no preventDefault: the page scrolls as normal */
    }
    e.preventDefault();
    var p = toCanvas(e.clientX, e.clientY);
    state = zoomAt(state, wheelFactor(e.deltaY, e.deltaMode), p.x, p.y, view);
    apply(false);
  }, { passive: false });

  /* Pointer drag, click-to-pin, and pinch. */
  var pointers = {}, dragStart = null, dragged = false, pinchStart = null;

  function pointerList() { return Object.keys(pointers).map(function (k) { return pointers[k]; }); }

  /* Cards are HTML inside the SVG. Pointer capture would redirect the click
     away from a link in a card, so leave anything that starts on a card alone. */
  function onCard(target) { return !!(target && target.closest && target.closest(".card")); }

  svg.addEventListener("pointerdown", function (e) {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    if (onCard(e.target)) return;
    if (e.pointerType === "touch" && !active) {
      /* Inactive map on touch: leave the finger to the browser so the page
         scrolls. A tap (pointerup with no cancel) activates the map. */
      var tapId = e.pointerId;
      var onUp = function (up) {
        if (up.pointerId !== tapId) return;
        cleanup();
        setActive(true);
        showHint("Map active: drag to move, pinch to zoom. Tap outside to release.");
      };
      var onCancel = function (c) { if (c.pointerId === tapId) cleanup(); };
      var cleanup = function () {
        svg.removeEventListener("pointerup", onUp);
        svg.removeEventListener("pointercancel", onCancel);
      };
      svg.addEventListener("pointerup", onUp);
      svg.addEventListener("pointercancel", onCancel);
      return;
    }
    setActive(true);
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
    if (onCard(e.target)) return;
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
      case "Escape": setPinned(null); setActive(false); return;
      default: return;
    }
    e.preventDefault();
    apply(false);
  }
  svg.addEventListener("keydown", onKey);
  if (toolbar) toolbar.addEventListener("keydown", onKey);
  /* Keyboard focus on the map, from Tab, counts as activation too. */
  svg.addEventListener("focus", function () { setActive(true); });

  /* Toolbar. */
  if (toolbar) {
    toolbar.removeAttribute("hidden");
    toolbar.addEventListener("click", function (e) {
      var button = e.target.closest ? e.target.closest("button") : null;
      if (!button) return;
      setActive(true);
      if (button.hasAttribute("data-preset")) goPreset(button.getAttribute("data-preset"), true);
      else if (button.getAttribute("data-zoom") === "in") { state = zoomAt(state, 1.5, view.x + view.w / 2, view.y + view.h / 2, view); apply(false); }
      else if (button.getAttribute("data-zoom") === "out") { state = zoomAt(state, 1 / 1.5, view.x + view.w / 2, view.y + view.h / 2, view); apply(false); }
    });
  }

  /* Cloud toggles are pure CSS. The script only remembers them across reloads. */
  var toggles = Array.prototype.slice.call(document.querySelectorAll(".cloud-toggles input[type=checkbox]"));
  if (toggles.length) {
    try {
      var hidden = JSON.parse(localStorage.getItem("statusboard.hiddenClouds") || "[]");
      toggles.forEach(function (box) { if (hidden.indexOf(box.id) >= 0) box.checked = false; });
    } catch (e) { /* ignore */ }
    toggles.forEach(function (box) {
      box.addEventListener("change", function () {
        var off = toggles.filter(function (b) { return !b.checked; }).map(function (b) { return b.id; });
        try { localStorage.setItem("statusboard.hiddenClouds", JSON.stringify(off)); } catch (e) { /* ignore */ }
      });
    });
  }

  /* Periodic reload. A meta refresh reloads regardless of what the reader is
     doing and resets focus, which fails accessibility checks, so the meta tag
     is kept only for browsers without scripts. Here the page reloads every
     two minutes, but only once the reader has been idle for a while and no
     card is pinned and the map is not active. Otherwise it tries again soon. */
  var RELOAD_MS = 120000, IDLE_MS = 30000, RETRY_MS = 20000;
  var lastInteraction = Date.now();
  ["pointerdown", "keydown", "wheel", "touchstart"].forEach(function (type) {
    document.addEventListener(type, function () { lastInteraction = Date.now(); }, { passive: true, capture: true });
  });
  function maybeReload() {
    var idle = Date.now() - lastInteraction >= IDLE_MS;
    if (idle && !active && !pinned && document.visibilityState !== "hidden") {
      location.reload();
    } else if (document.visibilityState === "hidden") {
      /* A hidden tab reloads when it comes back, not while nobody can see it. */
      document.addEventListener("visibilitychange", function once() {
        document.removeEventListener("visibilitychange", once);
        setTimeout(maybeReload, 500);
      });
    } else {
      setTimeout(maybeReload, RETRY_MS);
    }
  }
  setTimeout(maybeReload, RELOAD_MS);

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
