# ADR-0009: World map with region markers

## Goal

Draw a world map at the top of the dashboard. Put one marker per cloud region. Colour each marker by the worst open incident in that region. Render everything as inline SVG from Python at `render` time. No JavaScript, no map tiles, no CDN.

## Non-goals

- No pan or zoom.
- No continent or country shading. Regions are data centre clusters, not countries. Markers are the honest shape. Continent shading can be a later ADR.
- No per-service detail on the map. Tooltips name the incident titles only.
- No changes to the schema.

## Outcome shape

```
statusboard/data/world-110m.geojson      # vendored Natural Earth 1:110m countries
statusboard/data/world-land.svgpath      # generated once, one SVG path string, committed
statusboard/mapgen.py                    # projection, path generation, marker layout
statusboard/templates/index.html.j2      # gains one {{ map_svg | safe }} block
statusboard/render.py                    # build_context gains "map_svg"
tests/test_mapgen.py
Makefile                                 # new target: world-svg
```

## What carries over from previous specs

From ADR-0001: `db.open_incidents(conn)`, `Incident.regions` as `list[Region(cloud, code)]`, `Incident.provider`, `Incident.severity`.

From ADR-0005: `regions.all_regions()` giving `RegionInfo(cloud, code, name, lat, lon)`.

From ADR-0008: `build_context(conn, now)`, the `level` vocabulary `ok | minor | major | critical | stale`, the colour tokens, and the provider staleness rule.

## Implementation plan

1. Download Natural Earth 1:110m admin 0 countries as GeoJSON. One source is the `nvkelso/natural-earth-vector` GitHub repository, file `geojson/ne_110m_admin_0_countries.geojson`. Save it to `statusboard/data/`. Note the licence in the project `README.md`: Natural Earth is public domain.
2. Write `mapgen.py`:
   - `project(lon, lat, width, height) -> (x, y)` equirectangular. `x = (lon + 180) / 360 * width`, `y = (90 - lat) / 180 * height`.
   - `geojson_to_path(geojson, width, height) -> str` that walks every Polygon and MultiPolygon and emits `M x y L x y ... Z` with coordinates rounded to one decimal.
   - `land_path() -> str` that reads `world-land.svgpath` from package data.
   - `marker_layout(regions, levels) -> list[Marker]` where `levels` is `dict[(cloud, code), level]`.
   - `render_svg(markers, land, width, height, global_notes) -> str`.
3. Add `make world-svg` that runs `geojson_to_path` once and writes `world-land.svgpath`. Commit the output. `render` never parses the GeoJSON.
4. In `render.build_context`, compute `levels` and call `render_svg`. Put the result in `context["map_svg"]`.
5. Insert `{{ map_svg | safe }}` into the template between the header and the tiles.

## Behavioural definitions and contracts

### Canvas

Width 1000, height 500, `viewBox="0 0 1000 500"`, `width="100%"`, `preserveAspectRatio="xMidYMid meet"`. Clip latitude to [-60, 85] visually by translating and scaling the group so Antarctica does not waste a fifth of the canvas. Do this with a single `<g transform="...">` around the land path and markers, computed from the same projection.

### Land path

One `<path d="...">` with `fill: var(--map-land)` and `stroke: var(--map-stroke)`, `stroke-width 0.5`. Define `--map-land` and `--map-stroke` beside the ADR-0008 colour tokens, light and dark.

### Levels per region

For each open incident and each of its regions, `levels[(cloud, code)]` becomes the worst severity seen. Worst order: `critical > major > minor > ok`.

A Databricks incident carries `Region(cloud="aws", ...)`. It colours the AWS marker for that region. The tooltip names the incident, so the reader sees it is Databricks. Accept this for v1 and say so in the legend: `Databricks incidents are shown on their host cloud's marker`.

If the provider that owns a cloud is `stale` in the ADR-0008 sense, every marker for that cloud with level `ok` becomes `stale`. Markers with an incident keep their incident colour.

### Marker layout

One marker per row in `regions.csv`. Three clouds share many cities, so offset by cloud:

| cloud | dx, dy | shape |
|---|---|---|
| aws | 0, 0 | circle r=5 |
| gcp | +7, +5 | circle r=5 |
| azure | -7, +5 | circle r=5 |

Same shape, different offset. Colour is the level. Each marker gets `stroke: var(--map-stroke)` width 1 so adjacent markers stay distinct.

Each marker has a `<title>` child: `AWS us-east-1 (N. Virginia): ok` or `AWS us-east-1 (N. Virginia): critical. Multiple services: Increased Error Rates`. List up to three incident titles separated by `; `.

Markers with an incident render after all `ok` markers so they draw on top.

### Global incidents

An open incident with no regions is global. Show a line above the map: `Global: <provider> <title>` for each, with the severity colour. GitHub, Cloudflare, Claude, npm, and Docker incidents always land here.

### Legend

Below the map: five colour swatches with level names, then the three cloud offsets drawn as a mini cluster labelled `AWS`, `GCP`, `Azure`, then the Databricks note.

## Context7 lookups

- None needed. SVG path syntax and GeoJSON are stable. If unsure about `MultiPolygon` nesting, the GeoJSON RFC 7946 is the reference: Polygon is a list of rings, MultiPolygon is a list of Polygons, each ring is a list of `[lon, lat]`.

## Dependencies

- ADR-0005 and ADR-0008 complete.
- No new packages. The GeoJSON is data, not code.

## Test plan

`tests/test_mapgen.py`:

- `project(0, 0, 1000, 500) == (500, 250)`, `project(-180, 90, ...) == (0, 0)`, `project(180, -90, ...) == (1000, 500)`.
- `geojson_to_path` on a hand-written GeoJSON with one Polygon and one MultiPolygon emits the right number of `M` and `Z` commands.
- `marker_layout` with an empty `levels` gives one `ok` marker per region row.
- A `critical` aws `us-east-1` incident makes that marker `critical` and leaves gcp `us-east4` at `ok`.
- Two incidents on the same region, `minor` then `critical`, give `critical`.
- A stale gcp provider turns gcp `ok` markers to `stale` and leaves a gcp `major` marker as `major`.
- `render_svg` output contains one `<path` for land, N `<circle` elements, and a `<title>` for a chosen region.
- `build_context` includes `map_svg` and it starts with `<svg`.

## Acceptance criteria

- `make world-svg` writes `world-land.svgpath` under 400 KB.
- `make test` passes.
- `make refresh` renders a page with the map above the tiles. Markers sit on the right cities. Check at least: Dublin, Ashburn, Sydney, Tokyo, Sao Paulo.
- The page still makes exactly one network request.

## Gotchas

- GeoJSON is `[lon, lat]`, not `[lat, lon]`.
- Natural Earth includes Antarctica and tiny islands. The clip transform handles Antarctica. Islands are fine.
- Rounding to one decimal keeps the path small. Do not round to integers, coastlines go jagged.
- Equirectangular stretches the far north. That is acceptable. Do not add a Mercator projection.
- Keep marker radius fixed. Do not scale by incident count. That is a speculative feature.

## Handoff

This is the last planned ADR. Candidates for ADR-0010 and later, each as its own spec: continent shading, retention cleanup, account-specific health APIs, a JSON export for other tools. Do not start any of these without a spec.
