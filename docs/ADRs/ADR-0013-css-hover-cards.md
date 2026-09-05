# ADR-0013: Pure-CSS hover cards on the map

## Goal

Replace the native `<title>` tooltip with a real hover card. Cloud, region code, city, level chip, one line per open incident with a link, and a "Your region" tag. No JavaScript. The card appears on hover and on keyboard focus, stays open while the pointer moves onto it, and never hides behind other markers.

## Non-goals

- No JavaScript. Pinning a card on click is ADR-0012's job.
- No pan or zoom. ADR-0012.
- No data beyond what the page already has. Cards are built at render time from the same incidents as the markers.
- No schema changes.

## Outcome shape

```
statusboard/mapgen.py                      # cards layer, per-marker CSS rules, card placement
statusboard/render.py                      # passes map_css to the template
statusboard/templates/index.html.j2        # card styles, {{ map_css }} in the <style> block
tests/test_mapgen.py                       # extended
docs/ADRs/ADR-0012-zoomable-map.md         # its hover card section now points here
```

## What carries over from previous specs

From ADR-0009: `Marker(cloud, code, name, x, y, level, titles)`, `render_svg(markers, land, width, height)`, the `viewBox` crop from `y = 13.9` to `y = 416.7`, the `marker-<level>` classes, and the `<title>` child on each circle.

From ADR-0011: `Marker.mine` and the rule that an inactive filter makes every marker mine.

From ADR-0008: the colour tokens, the `.level-<level>` chip classes, and the rule that the page makes no external requests.

## Implementation plan

1. Extend `Marker` with `incidents: list[dict]` where each dict is `{title, url, severity, provider_label}`. `render.build_map_svg` fills it. Keep `titles` for the `<title>` fallback.
2. Give every circle a `data-key` attribute, `"<cloud>:<code>"`, and `tabindex="0"`.
3. After the markers, add one `<foreignObject>` that covers the cropped canvas. Inside it, one `<div class="cards">` holding one `<div class="card" data-key="...">` per marker. The card is HTML, so text wraps and links work.
4. Write `hover_css(markers) -> str` that returns one rule per marker. `render.py` passes it to the template as `map_css`, placed inside the page `<style>` block.
5. Compute card placement in Python. See contracts.
6. Update tests.

## Behavioural definitions and contracts

### Structure

```html
<svg class="map" viewBox="0 13.9 1000 402.8" ...>
  <path class="land" .../>
  <circle class="marker marker-major" data-key="aws:eu-west-2" tabindex="0" cx=".." cy=".." r="5">
    <title>AWS eu-west-2 (London): major. Increased API error rates</title>
  </circle>
  ...
  <foreignObject class="cards-layer" x="0" y="13.9" width="1000" height="402.8">
    <div xmlns="http://www.w3.org/1999/xhtml" class="cards">
      <div class="card" data-key="aws:eu-west-2" style="left: 52.4%; top: 22.1%">
        <div class="card-head"><b>AWS eu-west-2</b> <span class="muted">London</span></div>
        <span class="level level-major">major</span>
        <span class="mine-tag">Your region</span>
        <ul>
          <li><span class="level level-major">major</span> <a href="...">Increased API error rates</a></li>
        </ul>
      </div>
      ...
    </div>
  </foreignObject>
</svg>
```

The `xmlns` attribute on the inner `div` is required for `foreignObject` content.

### Showing a card

Cards are hidden with opacity and pointer events, never with `display: none`, so the pointer can travel from the marker onto the card.

```css
svg.map .cards-layer { pointer-events: none; overflow: visible; }
svg.map .card { position: absolute; width: 22%; opacity: 0; pointer-events: none;
                transition: opacity 0s linear 0.15s; }
svg.map .card:hover { opacity: 1; pointer-events: auto; transition-delay: 0s; }
```

One generated rule per marker:

```css
svg.map:has([data-key="aws:eu-west-2"]:hover) .card[data-key="aws:eu-west-2"],
svg.map:has([data-key="aws:eu-west-2"]:focus-visible) .card[data-key="aws:eu-west-2"] {
  opacity: 1; pointer-events: auto; transition-delay: 0s;
}
```

Why this shape. SVG paints in document order and has no `z-index`. A card inside a marker's own group would sit under every marker drawn later. Putting all cards in one layer at the end of the SVG puts them on top of everything. The `:has()` selector lets a hover on the marker reveal a card that is not its descendant. Keyboard focus on the circle does the same.

The 150 ms hide delay covers the pointer's trip across the gap between marker and card. The show has no delay.

`:has()` is supported by Chrome 105, Safari 15.4, and Firefox 121 or newer. Older browsers keep the `<title>` tooltip and never see a card. Do not add a JavaScript fallback.

### Placement

All numbers are canvas units on the 1000 by 402.8 cropped canvas, converted to percentages of the `foreignObject` for `left`, `right`, `top`, and `bottom`.

- Card width is 220 units, written as `width: 22%`.
- Horizontal: when `x <= 700`, `left = x + 8`. Otherwise `right = 1000 - x + 8`. The card opens away from the nearer edge.
- Vertical: when `y - 13.9 <= 260`, `top = y - 10`. Otherwise `bottom = 416.7 - y - 10`. The card grows downward in the top two thirds and upward in the bottom third.
- Convert with `left / 1000 * 100` and `top / 402.8 * 100`, one decimal place.

The card overlaps the marker by 2 units on the near side so there is no dead gap. That is why the offset is 8 while the marker radius is 5 or 6.

### Content

| Element | Source | Rule |
|---|---|---|
| head | cloud label, code, name | `AWS eu-west-2` bold, then the name muted |
| level chip | `Marker.level` | same classes as the tiles |
| Your region | `Marker.mine` | only when the filter is active and the marker is mine |
| incident list | `Marker.incidents` | up to five, newest first, each with a severity chip and the title linked to `url` when present |
| overflow | count beyond five | one line, `and N more` |
| quiet | no incidents | one muted line, `No open incidents` |

Everything is HTML-escaped by Jinja or by `html.escape` in `mapgen`. Cards are built in Python, not in the template, because `render_svg` already owns the SVG string.

### Styling

Cards use the surface, border, and ink tokens from ADR-0008. Font size is 11 canvas units, which renders at about 15 px when the map is 1350 px wide. Padding 8 units, radius 6 units, a 1 unit border. Add a subtle shadow in light mode only. In dark mode the border is enough.

The `<title>` children stay. They are the accessible name and the fallback.

## Context7 lookups

- None. This is CSS and inline SVG. If in doubt about `:has()` or `foreignObject`, MDN via web search.

## Dependencies

- ADR-0009 complete.
- ADR-0011 complete, for `Marker.mine`. If ADR-0011 is skipped, treat every marker as mine and omit the tag.
- No new packages.

## Test plan

`tests/test_mapgen.py` additions:

- Every circle has `data-key` equal to `cloud:code` and `tabindex="0"`.
- The SVG has exactly one `foreignObject` and it comes after the last `<circle>`.
- One `.card` per marker, keys match one to one.
- `hover_css` returns one rule per marker, each containing both `:hover` and `:focus-visible` selectors for its key.
- A marker at `x = 900` gets `right:` and no `left:`. A marker at `x = 100` gets `left:`.
- A marker at `y = 380` gets `bottom:`. A marker at `y = 100` gets `top:`.
- A card with six incidents lists five and `and 1 more`.
- A card with no incidents says `No open incidents`.
- A title containing `<b>` is escaped in the card and in the `<title>`.
- `mine=False` under an active filter omits `Your region`; `mine=True` includes it.

`tests/test_render.py`:

- The page contains the `:has(` rules and the count equals the marker count.
- The page still has no `<script>` tag. ADR-0012 changes that later, not this ADR.

## Acceptance criteria

- `make test` passes.
- `make refresh` produces a page under 400 KB. The cards add roughly 60 KB.
- In Chrome, Safari, and Firefox: hover a marker, see the card, move onto the card, click its link. Tab to a marker and see the card. Move away and the card hides.
- A card near the right edge opens to the left. A card near the bottom opens upward.
- The London cluster: hovering the Azure marker shows the Azure card, not the AWS one.

## Gotchas

- Do not put cards inside marker groups. They will be covered by later markers.
- Do not use `display: none` for hidden cards. The pointer cannot reach a card that is not there.
- `foreignObject` content needs the XHTML namespace on its root element or it will not render in some browsers.
- Percentage `top` and `bottom` inside `foreignObject` are relative to its height. Use the cropped height, 402.8, not 500.
- Card text scales with the map width. On a narrow phone it will be small. That is acceptable for v1; ADR-0012 can counter-scale.
- The `.level` chip class is shared with the tiles. Keep the chip CSS outside any `svg.map` scope so both places pick it up.

## Handoff

ADR-0012 must keep these cards readable under zoom. The cards layer sits outside the transformed viewport group, so ADR-0012 recomputes each card's `left` and `top` from the current transform, or moves the layer inside the group and counter-scales it. ADR-0012's own hover card section is replaced by a reference to this ADR, and its click-to-pin behaviour operates on these cards by toggling a `pinned` class.
