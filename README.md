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

## Database

Path comes from `STATUSBOARD_DB`, default `./statusboard.sqlite3`. Three tables: `incident`, `incident_region`, `poll_run`. See ADR-0001 for the schema and the rule that every column must have a reader and a writer.

## Data licences

`statusboard/data/world-110m.geojson` is Natural Earth 1:110m admin 0 countries, from the `nvkelso/natural-earth-vector` repository. Natural Earth is public domain. `world-land.svgpath` is generated from it by `make world-svg`.

## Deviations from the ADRs

- ADR-0004: no `aws_utf16_sample.bin` fixture. The test builds the UTF-16 bytes from the UTF-8 fixture at run time, so no binary file sits in git. Coverage is the same.

## Notes from implementation

- ADR-0002: the Statuspage docs do not state the order of `incident_updates`. The live GitHub feed, checked on 2026-09-05 across 12 incidents, is newest first. The provider reads index 0.
- ADR-0005: the Azure CLI was installed but its login had expired, so Azure coordinates are host-city proxies from the ADR table, not `az account list-locations` metadata. Hatchling packages `statusboard/data/regions.csv` by default; a wheel build confirmed it, so `pyproject.toml` needed no change.
- ADR-0006: Context7 has no status.io entry and developer.status.io is a JavaScript app with no static text. The incident shape was confirmed from a live status.io maintenance object, which uses the same fields. No named message-order constant exists: the provider sorts `messages` by `datetime` and takes the newest, so array order does not matter. The URL pattern `https://<host>/pages/incident/<page_id>/<incident_id>` returned 200 for a real incident. The Databricks GCP page writes `EU-West1` where GCP says `europe-west1`, so `regions.normalise` maps a leading `eu-` to `europe-` for gcp. `jioindiawest` was added to `regions.csv` because the Databricks Azure page lists it. After that, all 77 live container names resolve.
- ADR-0007: two Wayback Machine captures from July 2024 showed that each Azure RSS item carries `<category>` elements naming the affected regions with exact display names, plus the service name and sometimes `Public Non-Regional`. The provider reads regions from categories first and falls back to the ADR's text matching only when no category names a known region. The fixture `azure_items.xml` is built from those two real items, trimmed, plus one hand-written item without a `guid`.
- ADR-0008: labels come from a fixed list in `render.py`, with the Statuspage provider's own `label` attribute winning when present. Status colours are never used alone: every tile and severity cell also carries the level as text. `make refresh` uses `poll; render; exit $poll_code` so the page is rewritten even when one provider fails.
- ADR-0009: three small deviations. The latitude crop uses the SVG `viewBox` rather than a `<g transform>`, which is one attribute instead of a computed scale. Global incident lines are rendered by the Jinja template as HTML, not inside the SVG, so their titles can be links; `render_svg` therefore has no `global_notes` parameter. An incident counts as global when none of its regions is in the region table, so a GCP `global` location lands in the global list rather than vanishing. `world-land.svgpath` came out at 126 KB.
- ADR-0010: Context7 documents only incident.io's authenticated API, not its public Statuspage mimic. Checked live on 2026-09-05: `https://www.dockerstatus.com/incidents/<id>` returns 200 for a real incident id, so that is the URL fallback. `incident_updates` on Docker is newest first, same as Statuspage.
- ADR-0003: Context7 has no entry for the GCP status feed. The live feed on 2026-09-05 confirmed the three `status_impact` values in the ADR. The feed held 6 incidents, not hundreds, so no cutoff filter is needed.
