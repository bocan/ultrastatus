# statusboard

Polls the public status feeds of AWS, GCP, Azure, GitHub, and Databricks into one SQLite file, then renders one dashboard page. Python, standard library, cron-friendly.

The design lives in `docs/ADRs/`. Read `docs/ADRs/README.md` first.

## Quick start

```
make install
make init-db
make poll
make test
```

`make help` lists every target.

## Your regions

Copy `statusboard.example.toml` to `statusboard.toml` and list the regions you run in:

```toml
[regions]
aws   = ["eu-west-2", "us-east-1"]
gcp   = ["europe-west2"]
azure = ["uksouth"]
```

With the file present, the page puts your regions first: a banner says whether you are all clear, cloud tiles count incidents in your regions and mute the rest, your markers draw large and the others faint, and incidents elsewhere collapse under a details block. Without the file every region is treated equally. The path can be changed with `STATUSBOARD_CONFIG`. A typo in a region code stops `make render` with a suggestion. The filter applies at render time only, so the database keeps every incident.

## Database

Path comes from `STATUSBOARD_DB`, default `./statusboard.sqlite3`. Three tables: `incident`, `incident_region`, `poll_run`. See ADR-0001 for the schema and the rule that every column must have a reader and a writer.

## Data licences

`statusboard/data/world-50m.geojson` is Natural Earth 1:50m admin 0 countries, from the `nvkelso/natural-earth-vector` repository. Natural Earth is public domain. `world-land.svgpath` is generated from it by `make world-svg`. ADR-0009 used the 1:110m file; ADR-0012 moved to 1:50m so the coastline survives zoom.

## Deviations from the ADRs

- ADR-0004: no `aws_utf16_sample.bin` fixture. The test builds the UTF-16 bytes from the UTF-8 fixture at run time, so no binary file sits in git. Coverage is the same.

## Notes from implementation

- ADR-0002: the Statuspage docs do not state the order of `incident_updates`. The live GitHub feed, checked on 2026-09-05 across 12 incidents, is newest first. The provider reads index 0.
- ADR-0005: the Azure CLI was installed but its login had expired, so Azure coordinates are host-city proxies from the ADR table, not `az account list-locations` metadata. Hatchling packages `statusboard/data/regions.csv` by default; a wheel build confirmed it, so `pyproject.toml` needed no change.
- ADR-0006: Context7 has no status.io entry and developer.status.io is a JavaScript app with no static text. The incident shape was confirmed from a live status.io maintenance object, which uses the same fields. No named message-order constant exists: the provider sorts `messages` by `datetime` and takes the newest, so array order does not matter. The URL pattern `https://<host>/pages/incident/<page_id>/<incident_id>` returned 200 for a real incident. The Databricks GCP page writes `EU-West1` where GCP says `europe-west1`, so `regions.normalise` maps a leading `eu-` to `europe-` for gcp. `jioindiawest` was added to `regions.csv` because the Databricks Azure page lists it. After that, all 77 live container names resolve.
- ADR-0007: two Wayback Machine captures from July 2024 showed that each Azure RSS item carries `<category>` elements naming the affected regions with exact display names, plus the service name and sometimes `Public Non-Regional`. The provider reads regions from categories first and falls back to the ADR's text matching only when no category names a known region. The fixture `azure_items.xml` is built from those two real items, trimmed, plus one hand-written item without a `guid`.
- ADR-0008: labels come from a fixed list in `render.py`, with the Statuspage provider's own `label` attribute winning when present. Status colours are never used alone: every tile and severity cell also carries the level as text. `make refresh` uses `poll; render; exit $poll_code` so the page is rewritten even when one provider fails.
- ADR-0009: three small deviations. The latitude crop uses the SVG `viewBox` rather than a `<g transform>`, which is one attribute instead of a computed scale. Global incident lines are rendered by the Jinja template as HTML, not inside the SVG, so their titles can be links; `render_svg` therefore has no `global_notes` parameter. An incident counts as global when none of its regions is in the region table, so a GCP `global` location lands in the global list rather than vanishing. `world-land.svgpath` came out at 126 KB.
- ADR-0012: the page is 1.33 MB with the 1:50m countries file, under the 1.5 MB budget, so the land fallback was not needed. Cards are repositioned on every state change, all of them, not only the visible ones; 143 style writes per wheel event is cheap and the code is simpler. The label threshold is scale 5, not 3, because the Europe preset sits at about 3.1 and its labels overlapped. The viewport transform is set as a CSS `transform` style rather than the SVG attribute so the preset transition animates. Pinning is tested by hand, not under node.
- ADR-0012 follow-up, found by the user: links inside hover cards did nothing once the script was live. The pointerdown handler captured the pointer to the SVG for every press, and a capture redirects the following click away from the link. Pointer, wheel, and double-click handlers now ignore anything that starts inside a card. Proven under headless Chrome through the DevTools protocol: hover the marker, travel to the card, click the first line of the link, and the page navigated to the incident URL. The scratch driver scripts are not committed.
- ADR-0012 follow-up, found by the user: zoomed-in labels floated away from their dots. The 8 by 4 unit label offset was inside the zoomed group, so at 7x it became a 56 by 28 px gap and labels landed beside other regions' dots. The script now resets each label's `x` and `y` every frame to the marker centre plus a gap divided by the scale, the same trick as the radius. Measured under headless Chrome before and after.
- ADR-0012 follow-up, found by the user: wheel zoom was violent on a trackpad. The ADR said to use the sign of `deltaY` only, so every one of a swipe's many small events zoomed by a full 1.2x. The factor is now `exp(-deltaY * 0.0014)`, about 1.15x per 100 px mouse notch, capped at 1.5x per event. The ADR gotcha was corrected.
- ADR-0013 follow-up, found by the user: a card with one incident showed the severity chip twice, once as the region level and once on the incident line. The per-incident chip now appears only when a card lists more than one incident.
- ADR-0013 follow-up, found by the user: hover cards closed before the pointer reached a link. `pointer-events` cannot be transitioned, so it switched off the instant the pointer left the marker. Hidden cards now use `visibility` with a 450 ms grace period, and the card edge sits 4 units from the marker centre instead of 8 so there is no gap. The ADR text was corrected.
- ADR-0013: no deviations. The chip class is `.chip level-<level>` so the card and the global line share one rule. Cards are hidden with opacity and `pointer-events: none`, never `display: none`, and the 150 ms hide delay lets the pointer cross onto the card. Headless Chrome cannot hover, so the visual check forced three cards visible with an extra CSS rule in a scratch copy of the page. The page grew from 181 KB to 263 KB.
- ADR-0010: Context7 documents only incident.io's authenticated API, not its public Statuspage mimic. Checked live on 2026-09-05: `https://www.dockerstatus.com/incidents/<id>` returns 200 for a real incident id, so that is the URL fallback. `incident_updates` on Docker is newest first, same as Statuspage.
- ADR-0003: Context7 has no entry for the GCP status feed. The live feed on 2026-09-05 confirmed the three `status_impact` values in the ADR. The feed held 6 incidents, not hundreds, so no cutoff filter is needed.
