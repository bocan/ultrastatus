# ADR-0012: Zoomable map with hover cards and presets

## Goal

Turn the static map into something a person can use. Pan and zoom with the mouse, wheel, keyboard, and touch. Show a proper hover card for each marker with the incident titles as links. Offer one-click presets for the world, each continent, and the operator's own regions. Keep the page a single file with zero external requests.

## Non-goals

- No map tiles, no Leaflet, no MapLibre. Tiles need a tile server or a CDN, and both break the one-file, no-network rule.
- No live data fetching. The page still reloads every two minutes. Live patching is a separate ADR.
- No clustering. The cloud offsets from ADR-0009 already separate co-located markers, and zoom finishes the job.
- No schema changes.

## Outcome shape

```
statusboard/data/world-50m.geojson         # replaces world-110m.geojson
statusboard/data/world-land.svgpath        # regenerated from the 50m file
statusboard/mapgen.py                      # data attributes on markers, label elements, preset boxes
statusboard/templates/index.html.j2        # map toolbar, hover card element, one inline <script>
statusboard/static/map.js                  # the script source, inlined at render time
statusboard/render.py                      # reads map.js and passes it to the template
tests/test_mapgen.py                       # extended
tests/test_render.py                       # the no-script test changes, see below
tests/test_mapjs.py                        # runs the pure functions under node, skipped if node is absent
README.md                                  # data licence updated for 1:50m
```

## What carries over from previous specs

From ADR-0009: `project()`, `geojson_to_path()`, `marker_layout()`, `render_svg()`, the `viewBox` crop to latitude 85 to -60, the cloud offsets, `Marker.tooltip`, and the `marker-<level>` classes. The canvas is 1000 by 500 units before the crop.

From ADR-0011: `Marker.mine` and `my_region_labels`.

From ADR-0013: the cards layer, `data-key` on circles, `hover_css`, and the placement rules for `left`, `right`, `top`, and `bottom`.

From ADR-0008: the rule that the page makes no external requests. The rule that the page has no `<script>` tag is replaced by this ADR. See the test plan.

## Implementation plan

1. Replace the 1:110m GeoJSON with Natural Earth 1:50m admin 0 countries from the same repository, file `geojson/ne_50m_admin_0_countries.geojson`. Regenerate `world-land.svgpath` with `make world-svg`. Coordinates stay at one decimal. Check the size budget in the acceptance criteria. If it fails, fall back to `ne_50m_land.geojson`, which has no internal borders and is smaller.
2. In `mapgen.py`:
   - Wrap the land path and the markers in `<g class="viewport">`. The script transforms this group.
   - Circles already carry `data-key`, `tabindex`, and a `<title>` from ADR-0013. Nothing more is needed on them. The cards layer from ADR-0013 stays outside `g.viewport`.
   - Add a `<text class="label">` element after each circle with the region code, positioned 8 units right of the marker. Hidden by CSS until the zoom threshold.
   - Add `preset_boxes() -> dict[str, tuple[float, float, float, float]]` returning `(x, y, w, h)` in canvas units for `world`, `north-america`, `south-america`, `europe`, `middle-east-africa`, `asia`, `oceania`, and `mine`. `mine` is the bounding box of mine markers plus a 40 unit margin, or `world` when no filter is active. Continent boxes are fixed constants given below.
   - `render_svg` emits the presets as a `data-presets` JSON attribute on the `<svg>`.
3. Write `statusboard/static/map.js`. Plain JavaScript, no modules, no build step. Under 300 lines. Pure functions first, DOM code after, so tests can load the pure part under node.
4. In the template, add a toolbar above the map and the script inline at the end of the body: `<script>{{ map_js | safe }}</script>`.
5. In `render.py`, read `static/map.js` with `importlib.resources` and pass it as `map_js`.
6. Update tests.

## Behavioural definitions and contracts

### View state

One object drives everything:

```js
{ scale: 1, tx: 0, ty: 0 }   // viewport transform = translate(tx, ty) scale(scale)
```

`scale` is clamped to `[1, 8]`. At `scale = 1` the map fits the crop exactly and `tx = ty = 0`. Panning is clamped so the map never shows empty space beyond its edge. The transform is applied as a single attribute on `g.viewport`.

Pure functions, each exported on a `window.MapMath` object so tests can reach them:

```js
clampScale(s)                                   -> number in [1, 8]
zoomAt(state, factor, px, py, view)             -> new state, keeps the point (px, py) fixed under the cursor
panBy(state, dx, dy, view)                      -> new state, clamped to the map edge
fitBox(box, view)                               -> state that frames {x, y, w, h} with a 5% margin, scale clamped
```

`view` is `{x, y, w, h}` from the SVG `viewBox`.

### Input

| Input | Action |
|---|---|
| Wheel over the map | Cooperative: only when Cmd or Ctrl is held, or the map is active. Otherwise the event is left alone so the page scrolls, and a hint overlay shows for 1.4 s. When it does zoom: proportional to `deltaY`, `exp(-deltaY * 0.0014)`, about 1.15x per 100 px mouse notch, capped at 1.5x per event, centred on the cursor. `deltaMode` lines and pages are converted to a pixel estimate first. |
| Activation | A click or tap on the map, a toolbar button, or keyboard focus makes the map active, shown by a highlighted border. A pointer down outside the map and toolbar, or Escape, deactivates it. |
| Touch, inactive map | `touch-action: pan-y`, so one finger scrolls the page. A tap activates the map. |
| Touch, active map | `touch-action: none`, so one finger drags and two fingers pinch. |
| Drag | pan. Ignore drags under 3 px so a click is still a click. |
| Double click | zoom in by 2 at the cursor |
| Pinch (two touches) | zoom, centred between the fingers |
| Single touch drag | pan |
| `+` `-` keys, or the toolbar buttons | zoom by 1.5 at the centre |
| Arrow keys | pan by 10% of the view |
| `0` key, or the World button | reset to `world` |
| Escape | close a pinned hover card |

The SVG has `tabindex="0"` so keys work after a click. Keyboard handlers only fire when the SVG or its toolbar has focus.

### Markers at zoom

Markers keep a constant screen size. On every state change the script sets `r = baseRadius / scale` and `stroke-width = 1 / scale` on each circle, where `baseRadius` is 6 for mine and 4 for other. Labels get `font-size = 11 / scale` and are shown only when `scale >= 5`, through a `zoomed` class on the SVG. Their `x` and `y` are also reset each frame to the marker centre plus `9 / scale` and `4 / scale`, so the gap between dot and label stays 9 by 4 screen pixels. The static offset written by `mapgen` only serves the no-script page. Without this the gap grows with the zoom and, in a dense cluster, a label lands beside a different region's dot. The first draft said 3, but the Europe preset lands at about 3.1 and its 39 labels overlap into a pile. At 5 the cluster has spread enough to read. The cloud offsets are also divided by the scale each frame, so the nudge that separates three clouds in one city stays a constant 7 by 5 screen pixels. The first draft kept offsets in canvas units so markers would spread apart under zoom, but 7 canvas units is 2.5 degrees of longitude: at 7x the GCP London dot sat in France. Found by the user. Markers now converge on the true city as you zoom and stay visibly distinct.

### Hover card

The cards themselves come from ADR-0013, pure CSS, and already exist when this ADR runs. This ADR adds two things:

- **Pinning.** A click on a marker adds a `pinned` class to its card. A pinned card stays visible until Escape, a click elsewhere, or a click on another marker. CSS: `.card.pinned { opacity: 1; pointer-events: auto; }`.
- **Zoom-safe placement.** The cards layer is outside the transformed viewport group. On every state change the script recomputes each visible or pinned card's `left`, `right`, `top`, and `bottom` from the marker's canvas position and the current transform, using ADR-0013's placement rules. Cards keep constant screen size. Hidden cards are not repositioned until they show.

### Presets

Toolbar buttons: `World`, `N. America`, `S. America`, `Europe`, `Middle East & Africa`, `Asia`, `Oceania`, and `My regions` when the filter is active. Fixed boxes in canvas units, chosen to frame the markers with a margin. The implementer measures the marker extents from `regions.csv` and picks boxes that contain every marker in the group plus 30 units. Starting values:

| preset | x | y | w | h |
|---|---|---|---|---|
| world | 0 | 13.9 | 1000 | 402.8 |
| north-america | 130 | 90 | 330 | 200 |
| south-america | 260 | 250 | 200 | 190 |
| europe | 440 | 60 | 200 | 130 |
| middle-east-africa | 480 | 130 | 220 | 250 |
| asia | 640 | 60 | 300 | 230 |
| oceania | 830 | 300 | 170 | 130 |

The page opens on `world`, or on the view named in `location.hash`, for example `#view=europe`. Choosing a preset sets the hash. A hash the script does not know falls back to `world`. The last view is also saved to `localStorage` under `statusboard.view` and restored on load when there is no hash, so the two-minute reload does not lose the operator's zoom. Wrap every `localStorage` call in `try`.

### Reduced motion

Preset changes animate the transform over 250 ms. When `prefers-reduced-motion: reduce` matches, jump instead.

### No-script fallback

Without JavaScript the page is ADR-0009's map: static, `<title>` tooltips, no toolbar. The toolbar is rendered with `hidden` and the script removes the attribute. The CSS hides `.hover-card` and `.label` by default.

## Context7 lookups

- None for libraries. There are none.
- MDN, via web search if needed, for `WheelEvent.deltaMode`, `PointerEvent` for unified mouse and touch, and `SVGGraphicsElement.getScreenCTM()` to map cursor pixels to canvas units. Prefer pointer events over separate mouse and touch handlers.

## Dependencies

- ADR-0009, ADR-0011, and ADR-0013 complete.
- No new Python packages.
- `node` is optional, for `tests/test_mapjs.py` only. The test is skipped when `node` is not on the path.

## Test plan

`tests/test_mapgen.py` additions:

- A label element follows each circle with the region code.
- A click on a marker adds `pinned` to its card and to no other. Test this under node with a minimal DOM stub, or leave it to the manual checklist if the stub costs more than 30 lines.
- `preset_boxes()` returns the eight keys, and every marker in `regions.csv` for Europe falls inside the `europe` box. Repeat for `asia` and `north-america` using a fixed list of codes per continent in the test.
- With an active filter, the `mine` box contains every mine marker and no dimension is zero. With one mine marker the box still has the 40 unit margin.
- The `<svg>` carries `data-presets` that parses to the same dict.

`tests/test_render.py` change:

- Replace `assert "<script" not in html` with: exactly one `<script>` tag, it has no `src` attribute, and there is no `src="http` or `href="http` that points at a script or stylesheet. External links to status pages remain allowed.

`tests/test_mapjs.py`:

- Skip if `shutil.which("node")` is None.
- Write a small harness to `tmp_path` that defines `window = {}`, loads `map.js`, and calls `window.MapMath` functions. Assert:
  - `clampScale(0.5) == 1` and `clampScale(20) == 8`.
  - `zoomAt` at the view centre with factor 2 doubles `scale` and keeps the centre fixed.
  - `panBy` beyond the edge returns a clamped state that still covers the view.
  - `fitBox` on the `europe` box returns `scale > 1` and frames the box within the view.

Manual checklist, recorded in the ADR handoff when done:

- Wheel zoom keeps the point under the cursor still.
- Drag pans, clicks do not.
- Pinch works on a phone or in Chrome device mode.
- Hover card pins on click, closes on Escape, and stays the same screen size at 4x zoom.
- Labels appear at scale 5.
- Reload keeps the last view.
- With JavaScript disabled the map still renders with tooltips.

## Acceptance criteria

- `make test` passes.
- `site/index.html` is under 1.5 MB. If the 1:50m countries file pushes it over, use `ne_50m_land.geojson` and note it in the README.
- The browser network tab shows one request.
- Headless Chrome screenshots at `#view=europe` and `#view=asia` show the expected framing. Run: `chrome --headless=new --screenshot=out.png --window-size=1400,900 "file:///.../site/index.html#view=europe"`.
- The manual checklist is complete.

## Gotchas

- `getScreenCTM()` returns the matrix for the element, so call it on the `<svg>`, not the transformed group, then invert it to turn client pixels into canvas units before applying `zoomAt`.
- Wheel `deltaY` differs by device. Do not use the sign only. A trackpad or Magic Mouse fires dozens of small events per swipe, and a fixed factor per event zooms violently. Scale the factor by the delta so those small events add up to one gentle step.
- Pointer capture: call `setPointerCapture` on `pointerdown` so a drag that leaves the SVG keeps panning.
- Setting `r` on 150 circles per frame is fine. Do not rebuild the DOM.
- Keep the `<title>` child. It is the fallback and the accessible name.
- Do not animate with `requestAnimationFrame` loops. Set the transform once per input event, and use a CSS transition on the group for preset jumps only.
- The `meta refresh` reload still fires. The saved view restores it. Do not remove the refresh in this ADR.

## Handoff

The natural next ADR is live patching: the page fetches a small JSON every 60 seconds and updates tiles, tables, and marker classes in place, which ends the full reload. ADR-0008 ruled out a `data.json` output because nothing read it. That ADR would be the reader.
