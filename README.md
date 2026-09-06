# Ultra Status

One page that shows whether the services your work depends on are up, worldwide. It polls seventeen public status feeds into a SQLite file, then renders a single self-contained HTML page with a zoomable world map, grouped status tiles, and incident tables. Python, standard library plus Jinja2, and cron.

The page makes no network requests of its own. Everything, map included, is inline.

## What it watches

| Group | Providers |
|---|---|
| Clouds | AWS, GCP, Azure |
| Data platforms | Databricks, dbt Cloud, Snowflake, Airbyte |
| AI | Claude, OpenAI |
| Developer tooling | GitHub, Cloudflare, npm, Docker, PyPI |
| Workplace | Google Workspace, Slack, Atlassian |

All feeds are public. No API keys, no accounts. Each feed is polled once per run, or three times for Databricks, which runs one status page per host cloud, and twice for Snowflake, which needs its component list to place incidents on the map.

Incidents from AWS, GCP, Azure, Databricks, and Snowflake carry regions and appear on the map. The others are global and appear in a line above it.

## What the page shows

- **A world map** with one marker per cloud region, 143 of them across AWS, GCP, and Azure. Green is fine, amber is minor, orange is major, red is critical, grey means the feed is stale. Databricks and Snowflake incidents colour the marker of their host cloud region.
- **Hover cards** on every marker, with the region, its level, and each open incident linked to its status page. Pure CSS. Click a marker to pin its card.
- **Pan and zoom** with the wheel, drag, pinch, keyboard, or the preset buttons for the world, each continent, and your regions. Region codes appear at 5x. The view survives the two-minute reload.
- **Cloud toggles** in the map corner to hide or show AWS, GCP, or Azure markers.
- **Grouped tiles**, one per provider, with the worst open severity, the open count, and when it was last polled. A tile goes grey when its feed has not been polled for 15 minutes or the last poll failed.
- **Two tables**: open incidents, sorted by severity then recency, and everything resolved in the last 7 days.
- **Light and dark** follow the system preference.

## Quick start

```
make install        # create the virtualenv with uv
make refresh        # poll every feed, then write site/index.html
open site/index.html
make test           # 200+ tests, none touch the network
```

`make help` lists every target. `make poll` and `make render` are the two halves of `refresh`.

## Your regions

Copy `statusboard.example.toml` to `statusboard.toml` and list the regions you run in:

```toml
[regions]
aws   = ["eu-west-2", "us-east-1"]
gcp   = ["europe-west2"]
azure = ["uksouth"]
```

With the file present the page puts your regions first. A banner says whether you are all clear. Cloud tiles count incidents in your regions and show the rest as a muted "elsewhere" line. Your markers draw large and the others faint. Incidents elsewhere collapse under a details block. A "My regions" preset frames them on the map. Databricks and Snowflake incidents in your host cloud regions count as yours.

Without the file every region is treated equally. The filter applies at render time only, so the database keeps every incident and a config change applies to history. A typo in a region code stops `make render` with a suggestion. The path can be changed with `STATUSBOARD_CONFIG`.

## Running it from cron

```
*/2 * * * * cd /path/to/statusboard && PATH=/opt/homebrew/bin:$PATH make refresh >> /tmp/statusboard.log 2>&1
```

`docs/cron.md` covers the two things people get wrong: absolute paths and the `PATH` for `uv`. Two minutes is well inside every provider's limits. Statuspage, which hosts nine of the feeds, allows one request per second per page. Do not go below one minute.

`refresh` always renders, even when a feed fails, so the page keeps showing the last good data and marks that provider stale. Its exit code is the poll's.

## Database

Path comes from `STATUSBOARD_DB`, default `./statusboard.sqlite3`. Three tables: `incident`, `incident_region`, `poll_run`. There is no retention job yet; the file grows slowly. ADR-0001 holds the schema and the rule that every column must have a reader and a writer.

## Adding a provider

- **Runs on Atlassian Statuspage or incident.io?** One line in `statusboard/providers/statuspage.py` with the name, host, and label, plus one entry in `GROUPS` and `SOURCE_URLS` in `statusboard/render.py`. ADR-0017 is the worked example.
- **Anything else** gets a module under `statusboard/providers/`, a saved fixture, and a test file. ADR-0016 (Slack, custom JSON) and ADR-0019 (Airbyte, RSS) are the templates.
- A test fails by name if a provider is registered without a group, or listed in a group without a module.

## Licence

GPL. See `LICENSE`.
