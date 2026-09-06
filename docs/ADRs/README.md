# Statusboard ADRs

Each ADR is one session of work for a model. Run them in order. Each one lists what it inherits from earlier ones, so a fresh session has what it needs.

| ADR | Title | Adds |
|---|---|---|
| [0001](ADR-0001-project-skeleton.md) | Project skeleton | Package, Makefile, `Incident` model, SQLite schema, poll loop, fake provider tests |
| [0002](ADR-0002-github-provider.md) | GitHub provider | First live provider, Statuspage JSON |
| [0003](ADR-0003-gcp-provider.md) | GCP provider | First provider with regions |
| [0004](ADR-0004-aws-provider.md) | AWS provider | UTF-16 JSON feed, resolve-when-missing |
| [0005](ADR-0005-region-table.md) | Region table | `regions.csv` with coordinates, name normalisation |
| [0006](ADR-0006-databricks-provider.md) | Databricks provider | Three status.io pages merged into one provider |
| [0007](ADR-0007-azure-provider.md) | Azure provider | RSS parsing, region names found in text |
| [0008](ADR-0008-static-dashboard.md) | Static dashboard | `render` command, Jinja2 page, cron |
| [0009](ADR-0009-world-map.md) | World map | Inline SVG map with region markers |
| [0010](ADR-0010-statuspage-providers.md) | Statuspage providers | One class for GitHub, Cloudflare, Claude, npm, and Docker |
| [0011](ADR-0011-region-filter.md) | Region filter | `statusboard.toml` names your regions; tiles, tables, and map put them first |
| [0012](ADR-0012-zoomable-map.md) | Zoomable map | Pan, zoom, click-to-pin, and continent presets with one inline script |
| [0013](ADR-0013-css-hover-cards.md) | CSS hover cards | Real hover cards on the map with no JavaScript |
| [0014](ADR-0014-tile-groups.md) | Tile groups | Named tile groups with a status chip, and a guard that every provider has a group |
| [0015](ADR-0015-google-workspace-provider.md) | Google Workspace provider | GCP adapter refactored into one class with two instances |
| [0016](ADR-0016-slack-provider.md) | Slack provider | Slack's own status API, history endpoint |
| [0017](ADR-0017-statuspage-additions.md) | Statuspage additions | dbt Cloud, OpenAI, Atlassian, PyPI as four more instances |
| [0018](ADR-0018-snowflake-provider.md) | Snowflake provider | Statuspage subclass that maps component groups to regions |
| [0019](ADR-0019-airbyte-provider.md) | Airbyte provider | Instatus RSS history with the timeline parsed from the description |

ADR-0010 is out of numeric order on purpose. Run it after ADR-0004 and before ADR-0005, so the dashboard in ADR-0008 sees every provider.

ADR-0013 is also out of order. Run ADR-0011, then ADR-0013, then ADR-0012. The zoomable map builds on the cards.

ADR-0001 to ADR-0019 are all built. What each session found beyond its spec, and every deviation, is in [IMPLEMENTATION-NOTES.md](IMPLEMENTATION-NOTES.md).

## How to run one

Start a fresh session in the project root for each ADR. Use this prompt, changing the number:

```
Read docs/ADRs/ADR-0002-github-provider.md and implement it completely.
Follow the contracts exactly. Do not add database columns, files, or
features that the ADR does not name. Run `make test` and fix failures
before you finish. Do not start the next ADR. When done, list every
file you changed and any place you had to deviate from the spec.
```

Before starting ADR N, confirm ADR N-1 left `make test` green.

## Rules that apply to every ADR

- No speculative fields. A column, field, or file exists only if code in a named ADR reads or writes it.
- Standard library first. The only runtime package is `jinja2`, added in ADR-0008.
- Every provider has a saved fixture and tests that never touch the network.
- Timestamps are UTC, ISO 8601, truncated to seconds.
- Record any deviation from a spec in the project `README.md` so later sessions see it.
