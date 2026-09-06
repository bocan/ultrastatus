# Implementation notes

What each ADR session found that the spec did not say, and where the code deviates from the spec. Newest ADR first. Follow-ups found by the user sit under the ADR they touch.

## Marker offsets under zoom

- Found by the user: at the Europe preset the GCP europe-west2 dot sat in France. `regions.csv` has it at London; the culprit was the per-cloud nudge of 7 by 5 canvas units that keeps three clouds apart in one city. Canvas units scale with the map, and 7 of them is 2.5 degrees of longitude. The script now recovers each marker's true position from its cloud and re-applies the nudge divided by the scale, the same treatment the radius and labels already had, so the dots converge on the city as you zoom and stay 7 by 5 screen pixels apart. Cards follow the moved marker. The no-script map is unchanged at 1x.

## Accessibility audit

- Asked for by the user. Lighthouse's accessibility category, which runs axe-core, scored 0.9 with three findings: the `<meta http-equiv="refresh">`, 13 px checkboxes in the cloud toggles, and no `<main>` landmark. After the fixes it scores 1.0 with no failing audits.
- The meta refresh now sits inside `<noscript>`, so only browsers without scripts use it. The script reloads every two minutes instead, but only once the reader has been idle for 30 seconds with no pinned card and the map inactive; otherwise it retries every 20 seconds. A hidden tab reloads when it becomes visible again. The checkboxes are 24 px, the WCAG 2.2 minimum target size. The content between the header and footer is wrapped in `<main>`.
- Lighthouse lists ten manual checks it cannot automate: focus order, focus traps, visible focus, custom control labels and roles, and offscreen content. The page has no custom controls beyond the SVG markers, which carry `tabindex`, a `<title>`, and a visible focus ring.

## Cooperative map gestures

- Found by the user: two-finger scrolling with the pointer over the map zoomed the map and trapped the page. The fix is the rule embedded maps settled on years ago. A plain wheel scrolls the page and shows a hint; Cmd or Ctrl plus wheel zooms; clicking or tapping the map activates it so the wheel zooms until a click elsewhere or Escape. On touch the map uses `touch-action: pan-y` until activated, so one finger scrolls the page, and `none` after. ADR-0012's input table was updated.

## Open Graph board image

- Asked for by the user, no ADR. `statusboard/og.py` builds a 1200 by 630 SVG from `render.GROUPS`, and `make og-image` renders it to `statusboard/static/og.png` with headless Chrome on the dev machine, since crawlers accept neither SVG nor data URIs. `render` copies the PNG beside the page. The tags appear only when `[site] url` is set in `statusboard.toml`, because the page cannot know its own address. Column widths follow the longest text per column; equal widths made "DEVELOPER TOOLING" collide with "WORKPLACE".
- The IPv4 preference in `http.py` came from the same deployment day: the Debian EC2 host has a routed IPv6 address but TCP over v6 black-holes, which is still to be diagnosed.

## ADR-0019: Airbyte provider

- Airbyte runs on Instatus. Its Statuspage-style `api/v2/summary.json` returns only the page name and there is no incidents JSON, so the provider parses `history.rss`.
- Live on 2026-09-06 the feed held 50 items, 25 incidents and 25 maintenance windows, none open.
- Three parser rules came from live data. Maintenance items list the `Completed` entry first, so the newest entry is chosen by timestamp, with a terminal state winning ties. The year rollover only fires when an entry is more than seven days before `pubDate`, because maintenance entries can sit a few minutes before it; without that gap two old windows showed as open, one dated a year late. And any terminal entry resolves the item, because one window completed at 12:00 and then gained a note at 20:00. The ADR was corrected for all three.
- The fixture holds two live items plus one hand-edited open item, since nothing was open.

## ADR-0018: Snowflake provider

- No deviations. The Statuspage docs confirmed `group` and `group_id` on component objects.
- Live on 2026-09-06, all 53 group names matched the table, with `AWS GovCloud - DoD` dropped on purpose. The 50 live incidents produced region rows led by `aws us-west-2` with 18 and `azure eastus2` with 13.

## ADR-0017: dbt Cloud, OpenAI, Atlassian, PyPI

- No deviations. Live on 2026-09-06: dbt 25 incidents, OpenAI 25, Atlassian 34, PyPI 50, none open. The dbt fallback test reuses the Docker fixture rather than adding one.

## ADR-0016: Slack provider

- Context7 has no entry for the Slack Status API, only the Web API. Slack's own reference at docs.slack.dev confirmed the three `type` values and listed six `status` values, three more than the ADR assumed: `scheduled`, `completed`, and `cancelled` for maintenance. Completed and cancelled count as resolved; scheduled stays open. The ADR was updated.

## ADR-0015: Google Workspace provider

- No deviations. The Workspace feed writes its summary heading two ways, `**Summary:**` and `**Summary**`, so the title rule strips both, case-insensitively. Live on 2026-09-06 the feed held 46 incidents and the poll took under two seconds.

## ADR-0014: Tile groups

- One deviation. Groups flow side by side and wrap instead of stacking, because a stacked one-tile group wasted a whole row; the ADR text was updated. Getting there took two CSS attempts: a flex basis does not count toward a group's intrinsic width, so tiles carry a real width.
- `GROUPS` is the source of order and `PROVIDER_ORDER` is derived from it. The registration guard was checked by registering a fake provider in a scratch script: it failed with `registered but not in render.GROUPS: ['rogue']`.

## Map cloud toggles

- Asked for by the user. A small box in the map's top-right corner with an AWS, GCP, and Azure checkbox. Unchecking hides that cloud's markers, labels, and hover cards through a `:has(:not(:checked))` rule, so it works without JavaScript. The script only saves the choice to `localStorage` so the two-minute reload keeps it. Databricks and Snowflake have no toggle because their incidents draw on the host cloud's marker.

## ADR-0013: CSS hover cards

- No deviations at first. The chip class is `.chip level-<level>` so the card and the global line share one rule. Headless Chrome cannot hover, so the visual check forced three cards visible with an extra CSS rule in a scratch copy of the page. The page grew from 181 KB to 263 KB.
- Follow-up, found by the user: hover cards closed before the pointer reached a link. `pointer-events` cannot be transitioned, so it switched off the instant the pointer left the marker. Hidden cards now use `visibility` with a 450 ms grace period, and the card edge sits 4 units from the marker centre instead of 8 so there is no gap. The ADR text was corrected.
- Follow-up, found by the user: a card with one incident showed the severity chip twice, once as the region level and once on the incident line. The per-incident chip now appears only when a card lists more than one incident.

## ADR-0012: Zoomable map

- The page is 1.33 MB with the 1:50m countries file, under the 1.5 MB budget, so the land fallback was not needed. Cards are repositioned on every state change, all of them, not only the visible ones; 143 style writes per wheel event is cheap and the code is simpler. The label threshold is scale 5, not 3, because the Europe preset sits at about 3.1 and its labels overlapped. The viewport transform is set as a CSS `transform` style rather than the SVG attribute so the preset transition animates. Pinning is tested by hand, not under node.
- Follow-up, found by the user: links inside hover cards did nothing once the script was live. The pointerdown handler captured the pointer to the SVG for every press, and a capture redirects the following click away from the link. Pointer, wheel, and double-click handlers now ignore anything that starts inside a card. Proven under headless Chrome through the DevTools protocol: hover the marker, travel to the card, click the first line of the link, and the page navigated to the incident URL. The scratch driver scripts are not committed.
- Follow-up, found by the user: wheel zoom was violent on a trackpad. The ADR said to use the sign of `deltaY` only, so every one of a swipe's many small events zoomed by a full 1.2x. The factor is now `exp(-deltaY * 0.0014)`, about 1.15x per 100 px mouse notch, capped at 1.5x per event. The ADR gotcha was corrected.
- Follow-up, found by the user: zoomed-in labels floated away from their dots. The 8 by 4 unit label offset was inside the zoomed group, so at 7x it became a 56 by 28 px gap and labels landed beside other regions' dots. The script now resets each label's `x` and `y` every frame to the marker centre plus a gap divided by the scale, the same trick as the radius. Measured under headless Chrome before and after.

## ADR-0010: Statuspage providers

- Context7 documents only incident.io's authenticated API, not its public Statuspage mimic. Checked live on 2026-09-05: `https://www.dockerstatus.com/incidents/<id>` returns 200 for a real incident id, so that is the URL fallback. `incident_updates` on Docker is newest first, same as Statuspage.

## ADR-0009: World map

- Three small deviations. The latitude crop uses the SVG `viewBox` rather than a `<g transform>`, which is one attribute instead of a computed scale. Global incident lines are rendered by the Jinja template as HTML, not inside the SVG, so their titles can be links; `render_svg` therefore has no `global_notes` parameter. An incident counts as global when none of its regions is in the region table, so a GCP `global` location lands in the global list rather than vanishing. The 1:110m `world-land.svgpath` came out at 126 KB; ADR-0012 later replaced it with 1:50m.

## ADR-0008: Static dashboard

- Labels come from a fixed list in `render.py`, with the provider's own `label` attribute winning when present. Status colours are never used alone: every tile and severity cell also carries the level as text. `make refresh` uses `poll; render; exit $poll_code` so the page is rewritten even when one provider fails.

## ADR-0007: Azure provider

- Two Wayback Machine captures from July 2024 showed that each Azure RSS item carries `<category>` elements naming the affected regions with exact display names, plus the service name and sometimes `Public Non-Regional`. The provider reads regions from categories first and falls back to the ADR's text matching only when no category names a known region. The fixture `azure_items.xml` is built from those two real items, trimmed, plus one hand-written item without a `guid`.

## ADR-0006: Databricks provider

- Context7 has no status.io entry and developer.status.io is a JavaScript app with no static text. The incident shape was confirmed from a live status.io maintenance object, which uses the same fields. No named message-order constant exists: the provider sorts `messages` by `datetime` and takes the newest, so array order does not matter. The URL pattern `https://<host>/pages/incident/<page_id>/<incident_id>` returned 200 for a real incident.
- The Databricks GCP page writes `EU-West1` where GCP says `europe-west1`, so `regions.normalise` maps a leading `eu-` to `europe-` for gcp. `jioindiawest` was added to `regions.csv` because the Databricks Azure page lists it. After that, all 77 live container names resolve.

## ADR-0005: Region table

- The Azure CLI was installed but its login had expired, so Azure coordinates are host-city proxies from the ADR table, not `az account list-locations` metadata. Hatchling packages `statusboard/data/regions.csv` by default; a wheel build confirmed it, so `pyproject.toml` needed no change.

## ADR-0004: AWS provider

- One deviation: no `aws_utf16_sample.bin` fixture. The test builds the UTF-16 bytes from the UTF-8 fixture at run time, so no binary file sits in git. Coverage is the same. The live feed was UTF-16 BE with a byte order mark on the day of capture.

## ADR-0003: GCP provider

- Context7 has no entry for the GCP status feed. The live feed on 2026-09-05 confirmed the three `status_impact` values in the ADR. The feed held 6 incidents, not hundreds, so no cutoff filter is needed.

## ADR-0002: GitHub provider

- The Statuspage docs do not state the order of `incident_updates`. The live GitHub feed, checked on 2026-09-05 across 12 incidents, is newest first. The provider reads index 0.
